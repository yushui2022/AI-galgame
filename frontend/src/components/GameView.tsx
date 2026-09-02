import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft as ArrowLeftIcon,
  ArrowRight as ArrowRightIcon,
  ArrowsClockwise as ArrowsClockwiseIcon,
  GitBranch as GitBranchIcon,
  ImageSquare as ImageSquareIcon,
  PaperPlaneTilt as PaperPlaneTiltIcon,
  Sparkle as SparkleIcon,
  SkipForward as SkipForwardIcon,
  UploadSimple as UploadSimpleIcon,
  UserFocus as UserFocusIcon,
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
}

function latestAsset(turn: Turn | undefined, kind: "image" | "video") {
  return turn?.media_assets.filter((asset) => asset.kind === kind).at(-1) ?? null;
}

function isPlayableVideo(url: string | null | undefined) {
  return Boolean(url && /\.(mp4|webm|mov)(?:\?|$)/i.test(url));
}

export function GameView({ game, onBack, onGameChanged, onOpenProfile }: GameViewProps) {
  const [branches, setBranches] = useState<Branch[]>(game.branches);
  const [branchId, setBranchId] = useState<string | null>(
    game.branches.find((branch) => !branch.archived)?.id ?? null
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [uploadingCharacter, setUploadingCharacter] = useState<string | null>(null);
  const [generatingCharacters, setGeneratingCharacters] = useState(false);
  const [branchName, setBranchName] = useState("");
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
    source.onerror = () => setError("进度连接暂时中断，页面仍会保留当前存档");
    return () => {
      events.forEach((event) => source.removeEventListener(event, refresh));
      source.close();
    };
  }, [refreshTurns]);

  const current = turns.at(-1);
  const image = latestAsset(current, "image");
  const video = latestAsset(current, "video");
  const showVideo = isPlayableVideo(video?.url);

  useEffect(() => {
    if (!current || current.unlocked || current.media_status !== "ready" || showVideo) return;
    const timer = window.setTimeout(() => {
      void api.completeMedia(current.id).then(refreshTurns);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [current, refreshTurns, showVideo]);

  const submit = async (inputType: "suggested" | "free_text", text: string, choiceId?: string) => {
    if (!branchId || !current || busy) return;
    setBusy(true);
    setError(null);
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
      queued: "导演正在整理这一幕",
      generating_image: "正在生成场景画面",
      generating_video: "正在让画面动起来",
      retrying: "生成遇到波动，正在自动重试",
      failed: "媒体生成失败，可以重试或跳过",
      ready: "镜头已经就绪"
    };
    return messages[current.media_status] ?? "正在准备下一幕";
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
      className="game-page"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <header className="game-topbar">
        <div className="game-nav-left">
          <button className="icon-button" type="button" onClick={onBack} aria-label="返回故事库">
            <ArrowLeftIcon size={21} />
          </button>
          <div className="game-title">
            <span>{game.genre}</span>
            <strong>{game.title}</strong>
          </div>
        </div>
        <div className="game-nav-actions">
          <button className="text-button" type="button" onClick={() => setTimelineOpen(true)}>
            <GitBranchIcon size={19} />
            分支
          </button>
          <button className="icon-button" type="button" onClick={onOpenProfile} aria-label="玩家画像">
            <UserFocusIcon size={21} />
          </button>
        </div>
      </header>

      <div className="game-layout">
        <section className="media-column">
          <div className="media-stage">
            <AnimatePresence mode="wait">
              {showVideo && video?.url ? (
                <motion.video
                  key={video.id}
                  src={video.url}
                  autoPlay
                  playsInline
                  controls
                  onEnded={() => current && void api.completeMedia(current.id).then(refreshTurns)}
                  initial={reduceMotion ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                />
              ) : image?.url ? (
                <motion.img
                  key={image.id}
                  src={image.url}
                  alt={current?.scene ?? "当前剧情场景"}
                  initial={reduceMotion ? false : { opacity: 0, scale: 1.01 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                />
              ) : (
                <motion.div key="empty-stage" className="stage-placeholder" initial={false} animate={{ opacity: 1 }}>
                  <div className="scene-skeleton" />
                  <ImageSquareIcon size={34} weight="light" />
                </motion.div>
              )}
            </AnimatePresence>
            <div className="stage-scrim" />
            <div className="stage-status">
              <span>{current?.scene ?? "载入中"}</span>
              {!current?.unlocked && <p>{stageMessage}</p>}
            </div>
          </div>

          <div className="character-strip" aria-label="角色参考形象">
            {game.characters.map((character) => (
              <button
                key={character.id}
                type="button"
                className="character-chip"
                onClick={() => {
                  setUploadingCharacter(character.id);
                  fileInputRef.current?.click();
                }}
                title="上传角色参考图"
              >
                {character.reference_image_url ? (
                  <img src={character.reference_image_url} alt={character.name} />
                ) : (
                  <span>{character.name.slice(0, 1)}</span>
                )}
                <div>
                  <strong>{character.name}</strong>
                  <small>{character.role}</small>
                </div>
                <UploadSimpleIcon size={17} />
              </button>
            ))}
            {game.characters.some((character) => !character.reference_image_url) && (
              <button
                className="character-generate"
                type="button"
                disabled={generatingCharacters}
                onClick={() => void generateReferences()}
              >
                <SparkleIcon size={18} />
                {generatingCharacters ? "正在生成" : "生成缺失参考图"}
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
          </div>
        </section>

        <section className="story-column">
          {!current ? (
            <div className="story-loading">
              <div className="text-skeleton wide" />
              <div className="text-skeleton" />
              <div className="text-skeleton short" />
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.article
                key={current.id}
                className="story-beat"
                initial={reduceMotion ? false : { opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
              >
                <div className="turn-label">第 {current.turn_index + 1} 幕</div>
                <p className="narrative">{current.narrative}</p>
                <div className="dialogue-list">
                  {current.dialogue.map((line, index) => (
                    <div className="dialogue-line" key={`${line.speaker}-${index}`}>
                      <span>{line.speaker}</span>
                      <p>{line.text}</p>
                    </div>
                  ))}
                </div>

                {!current.unlocked ? (
                  <div className="locked-actions">
                    <p>{stageMessage}</p>
                    <div>
                      {current.media_status === "failed" && (
                        <button className="button secondary" type="button" onClick={() => void api.retryMedia(current.id)}>
                          <ArrowsClockwiseIcon size={18} />
                          重新生成
                        </button>
                      )}
                      <button
                        className="button ghost"
                        type="button"
                        onClick={() => void api.skipMedia(current.id).then(refreshTurns)}
                      >
                        <SkipForwardIcon size={18} />
                        跳过镜头
                      </button>
                    </div>
                  </div>
                ) : (
                  <ChoicePanel
                    choices={current.choices}
                    freeText={freeText}
                    setFreeText={setFreeText}
                    busy={busy}
                    onChoice={(choice) => void submit("suggested", choice.text, choice.id)}
                    onFree={() => void submit("free_text", freeText)}
                  />
                )}
              </motion.article>
            </AnimatePresence>
          )}
          {error && (
            <div className="story-error">
              <span>{error}</span>
              <button type="button" onClick={() => setError(null)} aria-label="关闭错误">
                <XIcon size={17} />
              </button>
            </div>
          )}
        </section>
      </div>

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
                    <button className="button secondary" type="button" onClick={() => void renameSelectedBranch()}>
                      保存名称
                    </button>
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
    </motion.section>
  );
}

interface ChoicePanelProps {
  choices: Choice[];
  freeText: string;
  setFreeText: (value: string) => void;
  busy: boolean;
  onChoice: (choice: Choice) => void;
  onFree: () => void;
}

function ChoicePanel({ choices, freeText, setFreeText, busy, onChoice, onFree }: ChoicePanelProps) {
  return (
    <div className="choice-panel">
      <div className="choice-list">
        {choices.map((choice, index) => (
          <button key={choice.id} type="button" disabled={busy} onClick={() => onChoice(choice)}>
            <span>{index + 1}</span>
            <strong>{choice.text}</strong>
            <ArrowRightIcon size={18} />
          </button>
        ))}
      </div>
      <form
        className="free-input"
        onSubmit={(event) => {
          event.preventDefault();
          if (freeText.trim()) onFree();
        }}
      >
        <label htmlFor="free-action">或者，亲自决定下一步</label>
        <div>
          <input
            id="free-action"
            value={freeText}
            onChange={(event) => setFreeText(event.target.value)}
            placeholder="描述你想尝试的行动"
            maxLength={1000}
          />
          <button type="submit" disabled={busy || !freeText.trim()} aria-label="提交自由行动">
            <PaperPlaneTiltIcon size={20} weight="fill" />
          </button>
        </div>
      </form>
      {busy && <p className="generation-note">故事正在回应你的选择</p>}
    </div>
  );
}
