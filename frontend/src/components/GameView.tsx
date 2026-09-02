import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft as ArrowLeftIcon,
  ArrowRight as ArrowRightIcon,
  ArrowsClockwise as ArrowsClockwiseIcon,
  CaretRight as CaretRightIcon,
  ChatCircleDots as ChatCircleDotsIcon,
  DotsThreeOutline as DotsThreeOutlineIcon,
  GearSix as GearSixIcon,
  GitBranch as GitBranchIcon,
  House as HouseIcon,
  ImageSquare as ImageSquareIcon,
  PaperPlaneTilt as PaperPlaneTiltIcon,
  SkipForward as SkipForwardIcon,
  Sparkle as SparkleIcon,
  UploadSimple as UploadSimpleIcon,
  UserFocus as UserFocusIcon,
  UsersThree as UsersThreeIcon,
  X as XIcon
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api } from "../api";
import type { Branch, Choice, Game, Turn } from "../types";

interface GameViewProps {
  game: Game;
  onBack: () => void;
  onGameChanged: () => void;
  onOpenProfile: () => void;
  onOpenSettings: () => void;
}

interface ScriptLine {
  speaker: string;
  text: string;
  emotion?: string;
  narration?: boolean;
}

function latestAsset(turn: Turn | undefined, kind: "image" | "video") {
  return turn?.media_assets.filter((asset) => asset.kind === kind).at(-1) ?? null;
}

function isPlayableVideo(url: string | null | undefined) {
  return Boolean(url && /\.(mp4|webm|mov)(?:\?|$)/i.test(url));
}

export function GameView({
  game,
  onBack,
  onGameChanged,
  onOpenProfile,
  onOpenSettings
}: GameViewProps) {
  const [branches, setBranches] = useState<Branch[]>(game.branches);
  const [branchId, setBranchId] = useState<string | null>(
    game.branches.find((branch) => !branch.archived)?.id ?? null
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [freeText, setFreeText] = useState("");
  const [freeInputOpen, setFreeInputOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [charactersOpen, setCharactersOpen] = useState(false);
  const [uploadingCharacter, setUploadingCharacter] = useState<string | null>(null);
  const [generatingCharacters, setGeneratingCharacters] = useState(false);
  const [branchName, setBranchName] = useState("");
  const [scriptIndex, setScriptIndex] = useState(0);
  const [visibleChars, setVisibleChars] = useState(0);
  const [videoFailed, setVideoFailed] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const reduceMotion = useReducedMotion();

  const activeBranches = useMemo(() => branches.filter((branch) => !branch.archived), [branches]);
  const archivedBranches = useMemo(() => branches.filter((branch) => branch.archived), [branches]);
  const selectedBranch = branches.find((branch) => branch.id === branchId) ?? null;

  const refreshBranches = useCallback(async () => {
    const next = await api.getBranches(game.id);
    const visible = next.filter((branch) => !branch.archived);
    setBranches(next);
    if ((!branchId || !visible.some((branch) => branch.id === branchId)) && visible[0]) {
      setBranchId(visible[0].id);
    }
    return next;
  }, [branchId, game.id]);

  const refreshTurns = useCallback(async () => {
    if (!branchId) return;
    setTurns(await api.getTurns(branchId));
  }, [branchId]);

  useEffect(() => {
    void refreshTurns();
  }, [refreshTurns]);

  useEffect(() => {
    setBranchName(selectedBranch?.name ?? "");
  }, [selectedBranch?.id, selectedBranch?.name]);

  useEffect(() => {
    const source = new EventSource("/api/events");
    const refresh = () => void refreshTurns();
    const events = ["turn.created", "media.image_ready", "media.video_ready", "media.failed", "turn.unlocked"];
    events.forEach((event) => source.addEventListener(event, refresh));
    source.onerror = () => setError("进度连接暂时中断，存档仍然安全，可以稍后刷新页面");
    return () => {
      events.forEach((event) => source.removeEventListener(event, refresh));
      source.close();
    };
  }, [refreshTurns]);

  const current = turns.at(-1);
  const image = latestAsset(current, "image");
  const video = latestAsset(current, "video");
  const shouldPlayVideo = Boolean(
    current && !current.unlocked && !videoFailed && isPlayableVideo(video?.url)
  );

  const scriptLines = useMemo<ScriptLine[]>(() => {
    if (!current) return [];
    return [
      ...(current.narrative
        ? [{ speaker: "旁白", text: current.narrative, narration: true } satisfies ScriptLine]
        : []),
      ...current.dialogue.map((line) => ({
        speaker: line.speaker,
        text: line.text,
        emotion: line.emotion
      }))
    ];
  }, [current]);

  const scriptComplete = scriptIndex >= scriptLines.length;
  const activeLine = scriptComplete ? null : scriptLines[scriptIndex];
  const lineComplete = Boolean(activeLine && visibleChars >= activeLine.text.length);
  const decisionReady = Boolean(current?.unlocked && scriptComplete);

  useEffect(() => {
    setScriptIndex(0);
    setVisibleChars(0);
    setFreeInputOpen(false);
    setVideoFailed(false);
  }, [current?.id]);

  useEffect(() => {
    if (!activeLine) return;
    if (reduceMotion) {
      setVisibleChars(activeLine.text.length);
      return;
    }
    setVisibleChars(0);
    const timer = window.setInterval(() => {
      setVisibleChars((count) => {
        const next = Math.min(count + 1, activeLine.text.length);
        if (next >= activeLine.text.length) window.clearInterval(timer);
        return next;
      });
    }, activeLine.narration ? 24 : 30);
    return () => window.clearInterval(timer);
  }, [activeLine?.narration, activeLine?.text, reduceMotion]);

  useEffect(() => {
    if (!current || current.unlocked || current.media_status !== "ready" || shouldPlayVideo) return;
    const timer = window.setTimeout(() => {
      void api.completeMedia(current.id).then(refreshTurns);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [current, refreshTurns, shouldPlayVideo]);

  const submit = async (inputType: "suggested" | "free_text", text: string, choiceId?: string) => {
    if (!branchId || !current || busy) return;
    setBusy(true);
    setError(null);
    setFreeInputOpen(false);
    try {
      const result = await api.submitTurn(branchId, {
        input_type: inputType,
        text,
        choice_id: choiceId,
        expected_head_turn_id: current.id
      });
      setTurns((existing) => [...existing, result.turn]);
      setFreeText("");
      await refreshBranches();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "剧情生成失败");
    } finally {
      setBusy(false);
    }
  };

  const advanceScript = () => {
    if (!activeLine) return;
    if (!lineComplete) {
      setVisibleChars(activeLine.text.length);
      return;
    }
    setScriptIndex((index) => Math.min(index + 1, scriptLines.length));
  };

  const skipMedia = async () => {
    if (!current) return;
    await api.skipMedia(current.id);
    await refreshTurns();
  };

  const retryMedia = async () => {
    if (!current) return;
    await api.retryMedia(current.id);
    await refreshTurns();
  };

  const forkAt = async (turn: Turn) => {
    if (!branchId) return;
    try {
      const branch = await api.forkBranch(branchId, turn.id);
      await refreshBranches();
      setBranchId(branch.id);
      setTimelineOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建分支失败");
    }
  };

  const chooseBranch = (id: string) => {
    setBranchId(id);
    setTimelineOpen(false);
  };

  const renameSelectedBranch = async () => {
    if (!selectedBranch || !branchName.trim()) return;
    try {
      await api.renameBranch(selectedBranch.id, branchName.trim());
      await refreshBranches();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分支重命名失败");
    }
  };

  const archiveSelectedBranch = async () => {
    if (!selectedBranch || activeBranches.length <= 1) return;
    try {
      await api.archiveBranch(selectedBranch.id);
      const next = await refreshBranches();
      setBranchId(next.find((branch) => !branch.archived)?.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分支归档失败");
    }
  };

  const restoreBranch = async (id: string) => {
    try {
      await api.restoreBranch(id);
      await refreshBranches();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分支恢复失败");
    }
  };

  const purgeBranch = async (branch: Branch) => {
    if (!window.confirm(`永久清理“${branch.name}”独占的剧情与媒体？此操作无法撤销。`)) return;
    try {
      await api.purgeBranch(branch.id);
      await refreshBranches();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分支清理失败");
    }
  };

  const stageMessage = useMemo(() => {
    if (!current) return "正在读取存档";
    const messages: Record<string, string> = {
      queued: "故事正在回应你的选择",
      generating_image: "光影与人物正在进入这一幕",
      generating_video: "时间开始在画面里流动",
      retrying: "这一幕正在重新形成",
      failed: "这一幕暂时无法显现",
      ready: "镜头已经就绪"
    };
    return messages[current.media_status] ?? "下一幕正在形成";
  }, [current]);

  const uploadReference = async (file: File) => {
    if (!uploadingCharacter) return;
    try {
      await api.uploadReference(game.id, uploadingCharacter, file);
      await onGameChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败");
    } finally {
      setUploadingCharacter(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const generateReferences = async () => {
    setGeneratingCharacters(true);
    setError(null);
    try {
      await api.generateCharacterReferences(game.id);
      await onGameChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "角色参考图生成失败");
    } finally {
      setGeneratingCharacters(false);
    }
  };

  return (
    <motion.section
      className="game-page game-cinematic"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="game-world" aria-label={current?.scene ?? "故事场景"}>
        <AnimatePresence mode="wait">
          {shouldPlayVideo && video?.url ? (
            <motion.video
              className="game-world-media"
              key={video.id}
              src={video.url}
              autoPlay
              muted
              playsInline
              disablePictureInPicture
              controlsList="nodownload noplaybackrate noremoteplayback"
              onEnded={() => current && void api.completeMedia(current.id).then(refreshTurns)}
              onError={() => setVideoFailed(true)}
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            />
          ) : image?.url ? (
            <motion.img
              className="game-world-media"
              key={image.id}
              src={image.url}
              alt={current?.scene ?? "当前剧情场景"}
              initial={reduceMotion ? false : { opacity: 0, scale: 1.025 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
            />
          ) : (
            <motion.div className="game-world-empty" key="empty-world" initial={false} animate={{ opacity: 1 }}>
              <div className="world-glow" />
              <ImageSquareIcon size={34} weight="light" />
            </motion.div>
          )}
        </AnimatePresence>
        <div className="game-world-vignette" />
        <div className="game-world-grain" />
      </div>

      <header className="game-hud">
        <button className="game-hud-button" type="button" onClick={onBack} aria-label="返回故事库">
          <ArrowLeftIcon size={20} />
        </button>
        <div className="game-hud-title">
          <span>第 {current ? current.turn_index + 1 : "—"} 幕</span>
          <strong>{game.title}</strong>
        </div>
        <div className="game-hud-scene">{current?.scene ?? "载入中"}</div>
        <button
          className="game-hud-button"
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="打开暂停菜单"
        >
          <DotsThreeOutlineIcon size={23} weight="fill" />
        </button>
      </header>

      {!current || (!current.unlocked && !shouldPlayVideo && current.media_status !== "ready") ? (
        <div className="forming-state" aria-live="polite">
          <span className="forming-mark"><i /><i /><i /></span>
          <strong>{stageMessage}</strong>
          <small>你可以先阅读这一幕，画面完成后会自动接入</small>
        </div>
      ) : null}

      {current && !current.unlocked && current.media_status !== "failed" && (
        <button className="scene-skip" type="button" onClick={() => void skipMedia()}>
          <SkipForwardIcon size={16} />
          跳过演出
        </button>
      )}

      {current?.media_status === "failed" && (
        <div className="scene-failed" role="alert">
          <div>
            <strong>这一幕没有成功显现</strong>
            <span>剧情存档没有丢失，可以重新生成或直接继续。</span>
          </div>
          <button type="button" onClick={() => void retryMedia()}>
            <ArrowsClockwiseIcon size={17} />重新生成
          </button>
          <button type="button" onClick={() => void skipMedia()}>继续剧情</button>
        </div>
      )}

      <main className="game-performance">
        <AnimatePresence mode="wait">
          {current && activeLine && (
            <motion.button
              className={activeLine.narration ? "vn-dialogue narration" : "vn-dialogue"}
              key={`${current.id}-${scriptIndex}`}
              type="button"
              onClick={advanceScript}
              aria-label={lineComplete ? "继续剧情" : "显示完整对白"}
              initial={reduceMotion ? false : { opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
            >
              <span className="vn-speaker">
                {activeLine.speaker}
                {activeLine.emotion && <small>{activeLine.emotion}</small>}
              </span>
              <span className="vn-line">{activeLine.text.slice(0, visibleChars)}</span>
              <span className={lineComplete ? "vn-continue ready" : "vn-continue"}>
                <CaretRightIcon size={18} weight="bold" />
              </span>
              <span className="vn-progress" aria-hidden="true">
                {scriptLines.map((_, index) => <i className={index <= scriptIndex ? "active" : ""} key={index} />)}
              </span>
            </motion.button>
          )}

          {current && scriptComplete && !current.unlocked && current.media_status !== "failed" && (
            <motion.div
              className="vn-waiting"
              key="waiting-for-scene"
              initial={reduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <span className="forming-mark compact"><i /><i /><i /></span>
              <div>
                <strong>{stageMessage}</strong>
                <small>镜头结束后，选择才会出现</small>
              </div>
            </motion.div>
          )}

          {current && decisionReady && (
            <DecisionPanel
              key={`${current.id}-decision`}
              choices={current.choices}
              freeText={freeText}
              setFreeText={setFreeText}
              freeInputOpen={freeInputOpen}
              setFreeInputOpen={setFreeInputOpen}
              busy={busy}
              onChoice={(choice) => void submit("suggested", choice.text, choice.id)}
              onFree={() => void submit("free_text", freeText)}
            />
          )}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {busy && (
          <motion.div
            className="story-forming-curtain"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <span className="forming-mark"><i /><i /><i /></span>
            <strong>你的选择正在改变故事</strong>
            <small>正在判断行动、续写人物与整理下一幕</small>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <div className="game-toast" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">
            <XIcon size={17} />
          </button>
        </div>
      )}

      <AnimatePresence>
        {menuOpen && (
          <div className="game-pause-backdrop" role="presentation" onMouseDown={() => setMenuOpen(false)}>
            <motion.aside
              className="game-pause-menu"
              role="dialog"
              aria-modal="true"
              aria-label="暂停菜单"
              initial={reduceMotion ? false : { opacity: 0, scale: 0.96, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98 }}
              onMouseDown={(event) => event.stopPropagation()}
            >
              <header>
                <div>
                  <span>PAUSED</span>
                  <h2>{game.title}</h2>
                </div>
                <button type="button" onClick={() => setMenuOpen(false)} aria-label="继续游戏">
                  <XIcon size={20} />
                </button>
              </header>
              <nav>
                <button type="button" onClick={() => { setMenuOpen(false); setTimelineOpen(true); }}>
                  <GitBranchIcon size={21} /><span><strong>故事分支</strong><small>查看时间线或从过去继续</small></span><CaretRightIcon />
                </button>
                <button type="button" onClick={() => { setMenuOpen(false); onOpenProfile(); }}>
                  <UserFocusIcon size={21} /><span><strong>玩家画像</strong><small>查看系统记住的偏好</small></span><CaretRightIcon />
                </button>
                <button type="button" onClick={() => { setMenuOpen(false); setCharactersOpen(true); }}>
                  <UsersThreeIcon size={21} /><span><strong>角色设定</strong><small>管理角色参考形象</small></span><CaretRightIcon />
                </button>
                <button type="button" onClick={onOpenSettings}>
                  <GearSixIcon size={21} /><span><strong>模型设置</strong><small>更换剧情与媒体 Provider</small></span><CaretRightIcon />
                </button>
                <button type="button" onClick={onBack}>
                  <HouseIcon size={21} /><span><strong>返回故事库</strong><small>当前进度已自动保存</small></span><CaretRightIcon />
                </button>
              </nav>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {timelineOpen && (
          <div className="drawer-backdrop" role="presentation" onMouseDown={() => setTimelineOpen(false)}>
            <motion.aside
              className="timeline-drawer"
              initial={reduceMotion ? false : { x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              onMouseDown={(event) => event.stopPropagation()}
            >
              <header>
                <div>
                  <h2>故事分支</h2>
                  <p>从任何已经发生的回合继续，不会复制公共媒体。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => setTimelineOpen(false)} aria-label="关闭">
                  <XIcon size={20} />
                </button>
              </header>
              <div className="branch-switcher">
                {activeBranches.map((branch) => (
                  <button
                    key={branch.id}
                    type="button"
                    className={branch.id === branchId ? "active" : ""}
                    onClick={() => chooseBranch(branch.id)}
                  >
                    {branch.name}
                  </button>
                ))}
              </div>
              {selectedBranch && (
                <div className="branch-management">
                  <label>
                    <span>当前分支名称</span>
                    <input value={branchName} onChange={(event) => setBranchName(event.target.value)} />
                  </label>
                  <div>
                    <button className="button secondary" type="button" onClick={() => void renameSelectedBranch()}>保存名称</button>
                    <button
                      className="button ghost"
                      type="button"
                      disabled={activeBranches.length <= 1}
                      onClick={() => void archiveSelectedBranch()}
                    >
                      归档分支
                    </button>
                  </div>
                  {activeBranches.length <= 1 && <small>至少保留一条可玩的分支。</small>}
                </div>
              )}
              <div className="turn-timeline">
                {[...turns].reverse().map((turn) => (
                  <div className="timeline-item" key={turn.id}>
                    <div>
                      <span>第 {turn.turn_index + 1} 幕</span>
                      <strong>{turn.scene}</strong>
                      <p>{turn.narrative}</p>
                    </div>
                    <button className="icon-button" type="button" onClick={() => void forkAt(turn)} aria-label="从这里创建分支">
                      <GitBranchIcon size={18} />
                    </button>
                  </div>
                ))}
              </div>
              {archivedBranches.length > 0 && (
                <div className="archived-branches">
                  <h3>已归档</h3>
                  {archivedBranches.map((branch) => (
                    <div key={branch.id}>
                      <span>{branch.name}</span>
                      <button type="button" onClick={() => void restoreBranch(branch.id)}>恢复</button>
                      <button className="danger-text" type="button" onClick={() => void purgeBranch(branch)}>永久清理</button>
                    </div>
                  ))}
                </div>
              )}
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {charactersOpen && (
          <div className="drawer-backdrop" role="presentation" onMouseDown={() => setCharactersOpen(false)}>
            <motion.aside
              className="character-drawer"
              initial={reduceMotion ? false : { x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              onMouseDown={(event) => event.stopPropagation()}
            >
              <header>
                <div>
                  <h2>角色设定</h2>
                  <p>参考形象只用于保持后续场景中的角色一致性。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => setCharactersOpen(false)} aria-label="关闭">
                  <XIcon size={20} />
                </button>
              </header>
              <div className="character-manager-list">
                {game.characters.map((character) => (
                  <article key={character.id}>
                    {character.reference_image_url ? (
                      <img src={character.reference_image_url} alt={`${character.name}的参考形象`} />
                    ) : (
                      <span>{character.name.slice(0, 1)}</span>
                    )}
                    <div>
                      <strong>{character.name}</strong>
                      <small>{character.role}</small>
                      <p>{character.personality || character.appearance || "尚未补充角色细节"}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setUploadingCharacter(character.id);
                        fileInputRef.current?.click();
                      }}
                    >
                      <UploadSimpleIcon size={17} />
                      {character.reference_image_url ? "替换" : "上传"}
                    </button>
                  </article>
                ))}
              </div>
              {game.characters.some((character) => !character.reference_image_url) && (
                <button
                  className="button primary character-generate-action"
                  type="button"
                  disabled={generatingCharacters}
                  onClick={() => void generateReferences()}
                >
                  <SparkleIcon size={18} />
                  {generatingCharacters ? "正在生成参考形象" : "生成缺失参考形象"}
                </button>
              )}
              <input
                ref={fileInputRef}
                className="visually-hidden"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadReference(file);
                }}
              />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

interface DecisionPanelProps {
  choices: Choice[];
  freeText: string;
  setFreeText: (value: string) => void;
  freeInputOpen: boolean;
  setFreeInputOpen: (value: boolean) => void;
  busy: boolean;
  onChoice: (choice: Choice) => void;
  onFree: () => void;
}

function DecisionPanel({
  choices,
  freeText,
  setFreeText,
  freeInputOpen,
  setFreeInputOpen,
  busy,
  onChoice,
  onFree
}: DecisionPanelProps) {
  return (
    <motion.section
      className="decision-panel"
      aria-label="选择下一步"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
    >
      <header>
        <span>YOUR DECISION</span>
        <h2>你准备怎么做？</h2>
      </header>
      <div className="decision-list">
        {choices.map((choice, index) => (
          <button key={choice.id} type="button" disabled={busy} onClick={() => onChoice(choice)}>
            <span>0{index + 1}</span>
            <strong>{choice.text}</strong>
            <ArrowRightIcon size={20} />
          </button>
        ))}
      </div>
      <button
        className={freeInputOpen ? "custom-action active" : "custom-action"}
        type="button"
        onClick={() => setFreeInputOpen(!freeInputOpen)}
        aria-expanded={freeInputOpen}
      >
        <ChatCircleDotsIcon size={19} />
        自定义行动
        <small>不受选项限制</small>
      </button>
      <AnimatePresence>
        {freeInputOpen && (
          <motion.form
            className="free-action-form"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={(event) => {
              event.preventDefault();
              if (freeText.trim()) onFree();
            }}
          >
            <label htmlFor="free-action">或者，亲自决定下一步</label>
            <div>
              <textarea
                id="free-action"
                value={freeText}
                onChange={(event) => setFreeText(event.target.value)}
                placeholder="描述你想尝试的行动……"
                maxLength={1000}
                rows={2}
                autoFocus
              />
              <button type="submit" disabled={busy || !freeText.trim()} aria-label="提交自由行动">
                <PaperPlaneTiltIcon size={20} weight="fill" />
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
