import { useState } from "react";
import {
  ArrowRight as ArrowRightIcon,
  BookOpenText as BookOpenTextIcon,
  GearSix as GearSixIcon,
  Plus as PlusIcon,
  UserFocus as UserFocusIcon,
  X as XIcon
} from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { api } from "../api";
import type { CharacterInput, Game, GameCreatePayload } from "../types";

interface HomeViewProps {
  games: Game[];
  onOpenSettings: () => void;
  onOpenProfile: () => void;
  onOpenGame: (id: string) => void;
  onCreated: (game: Game) => void;
}

const CUSTOM_DEFAULT: GameCreatePayload = {
  mode: "custom",
  title: "",
  genre: "校园悬疑恋爱",
  premise: "",
  world_rules: "现代背景，世界规律稳定，所有关键谜题必须留下可验证线索，全年龄内容。",
  art_style: "日系动画电影感，细腻光影，16:9构图",
  characters: []
};

const EMPTY_CHARACTER: CharacterInput = {
  name: "",
  role: "主要角色",
  personality: "",
  appearance: "",
  background: ""
};

export function HomeView({
  games,
  onOpenSettings,
  onOpenProfile,
  onOpenGame,
  onCreated
}: HomeViewProps) {
  const [creating, setCreating] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [custom, setCustom] = useState<GameCreatePayload>(CUSTOM_DEFAULT);
  const [error, setError] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const createTemplate = async () => {
    setCreating(true);
    setError(null);
    try {
      onCreated(
        await api.createGame({
          ...CUSTOM_DEFAULT,
          mode: "template",
          title: "旧校舍的第七码",
          premise: "转学生在雨夜收到一条来自失踪学姐的短信，并与总在旧校舍出现的少女共同追查真相。"
        })
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const createCustom = async () => {
    if (!custom.title.trim() || !custom.premise.trim()) {
      setError("请填写故事名称和核心设定");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      onCreated(await api.createGame(custom));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const updateCharacter = (index: number, patch: Partial<CharacterInput>) => {
    setCustom((current) => ({
      ...current,
      characters: current.characters.map((character, characterIndex) =>
        characterIndex === index ? { ...character, ...patch } : character
      )
    }));
  };

  return (
    <motion.section
      className="library-page"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <span>AI Galgame</span>
        </div>
        <nav>
          <button className="icon-button" type="button" onClick={onOpenProfile} aria-label="玩家画像">
            <UserFocusIcon size={22} />
          </button>
          <button className="icon-button" type="button" onClick={onOpenSettings} aria-label="模型设置">
            <GearSixIcon size={22} />
          </button>
        </nav>
      </header>

      <div className="library-intro">
        <p className="eyebrow">你的故事库</p>
        <h1>故事会记住你的选择。</h1>
        <p>选择一个旧世界继续，或者让模型从一个念头开始创造新的校园传说。</p>
      </div>

      <div className="starter-grid">
        <article className="template-feature">
          <div className="template-visual" aria-hidden="true">
            <span className="rain-line one" />
            <span className="rain-line two" />
            <span className="window-light" />
            <div className="template-title">第七码</div>
          </div>
          <div className="template-copy">
            <span>校园悬疑恋爱</span>
            <h2>旧校舍的第七码</h2>
            <p>失踪一年的学姐发来短信。雨夜、旧校舍与一名隐瞒真相的少女正在等你。</p>
            <button className="button primary" type="button" disabled={creating} onClick={() => void createTemplate()}>
              {creating ? "正在创建" : "进入雨夜"}
              <ArrowRightIcon size={18} />
            </button>
          </div>
        </article>

        <button className="custom-starter" type="button" onClick={() => setCustomOpen(true)}>
          <PlusIcon size={30} weight="light" />
          <strong>自由创建</strong>
          <span>输入世界、角色和画风</span>
        </button>
      </div>

      <section className="saved-section">
        <div className="section-heading">
          <h2>继续游玩</h2>
          <span>{games.length} 个世界</span>
        </div>
        {games.length === 0 ? (
          <div className="empty-state">
            <BookOpenTextIcon size={34} weight="light" />
            <p>还没有保存的故事。上面的雨夜可以成为第一段记忆。</p>
          </div>
        ) : (
          <div className="game-list">
            {games.map((game) => (
              <button key={game.id} className="game-row" type="button" onClick={() => onOpenGame(game.id)}>
                <div>
                  <span>{game.genre}</span>
                  <strong>{game.title}</strong>
                  <p>{game.premise}</p>
                </div>
                <div className="game-row-meta">
                  <span>{game.branches.filter((branch) => !branch.archived).length} 条分支</span>
                  <ArrowRightIcon size={20} />
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {error && <p className="floating-error">{error}</p>}

      {customOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCustomOpen(false)}>
          <motion.form
            className="modal custom-modal"
            onSubmit={(event) => {
              event.preventDefault();
              void createCustom();
            }}
            initial={reduceMotion ? false : { opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <h2>创造一个新世界</h2>
                <p>先给模型清晰的冲突和规则，角色会在游玩中逐渐生长。</p>
              </div>
              <button className="icon-button" type="button" onClick={() => setCustomOpen(false)} aria-label="关闭">
                <XIcon size={20} />
              </button>
            </header>
            <div className="form-grid">
              <label>
                <span>故事名称</span>
                <input value={custom.title} onChange={(event) => setCustom({ ...custom, title: event.target.value })} />
              </label>
              <label>
                <span>题材</span>
                <input value={custom.genre} onChange={(event) => setCustom({ ...custom, genre: event.target.value })} />
              </label>
              <label className="wide">
                <span>核心设定</span>
                <textarea rows={4} value={custom.premise} onChange={(event) => setCustom({ ...custom, premise: event.target.value })} />
              </label>
              <label className="wide">
                <span>世界规则</span>
                <textarea rows={3} value={custom.world_rules} onChange={(event) => setCustom({ ...custom, world_rules: event.target.value })} />
              </label>
              <label className="wide">
                <span>画面风格</span>
                <input value={custom.art_style} onChange={(event) => setCustom({ ...custom, art_style: event.target.value })} />
              </label>
              <div className="character-editor wide">
                <div className="character-editor-heading">
                  <div>
                    <strong>持续出镜角色</strong>
                    <span>可选，最多3名。留空时会使用示例角色。</span>
                  </div>
                  <button
                    className="text-button"
                    type="button"
                    disabled={custom.characters.length >= 3}
                    onClick={() =>
                      setCustom((current) => ({
                        ...current,
                        characters: [...current.characters, { ...EMPTY_CHARACTER }]
                      }))
                    }
                  >
                    <PlusIcon size={17} />
                    添加角色
                  </button>
                </div>
                {custom.characters.map((character, index) => (
                  <div className="character-editor-card" key={index}>
                    <div className="character-editor-card-title">
                      <span>角色 {index + 1}</span>
                      <button
                        type="button"
                        aria-label={`移除角色 ${index + 1}`}
                        onClick={() =>
                          setCustom((current) => ({
                            ...current,
                            characters: current.characters.filter((_, itemIndex) => itemIndex !== index)
                          }))
                        }
                      >
                        <XIcon size={16} />
                      </button>
                    </div>
                    <div className="character-fields">
                      <label>
                        <span>姓名</span>
                        <input required value={character.name} onChange={(event) => updateCharacter(index, { name: event.target.value })} />
                      </label>
                      <label>
                        <span>身份</span>
                        <input value={character.role} onChange={(event) => updateCharacter(index, { role: event.target.value })} />
                      </label>
                      <label>
                        <span>性格</span>
                        <input value={character.personality} onChange={(event) => updateCharacter(index, { personality: event.target.value })} />
                      </label>
                      <label>
                        <span>外观</span>
                        <input value={character.appearance} onChange={(event) => updateCharacter(index, { appearance: event.target.value })} />
                      </label>
                    </div>
                    <label>
                      <span>背景与秘密</span>
                      <textarea rows={2} value={character.background} onChange={(event) => updateCharacter(index, { background: event.target.value })} />
                    </label>
                  </div>
                ))}
              </div>
            </div>
            <div className="form-actions">
              <button className="button secondary" type="button" onClick={() => setCustomOpen(false)}>取消</button>
              <button className="button primary" type="submit" disabled={creating}>
                {creating ? "正在创建" : "生成开场"}
              </button>
            </div>
          </motion.form>
        </div>
      )}
    </motion.section>
  );
}
