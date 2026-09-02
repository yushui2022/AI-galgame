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
  genre: "校园恋爱",
  premise: "",
  world_rules: "现代高中校园，以日常相处、社团活动、节日和恋爱关系发展为主；不主动引入悬疑、犯罪、失踪、超自然或阴谋；全年龄内容。",
  art_style: "日系青春恋爱动画，春日校园，樱花与暖阳，清透明亮，柔和粉蓝色调，16:9构图",
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
          title: "樱花落下之前",
          premise: "新学期开始，你在日常相处、社团活动和校园文化祭的准备中，与三位性格不同的同学逐渐靠近。你的每个选择都会改变彼此的关系与共同回忆。"
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
        <p>选择一个旧故事继续，或者从一次心动开始创造新的校园回忆。</p>
      </div>

      <div className="starter-grid">
        <article className="template-feature">
          <div className="template-visual" aria-hidden="true">
            <span className="spring-petal one" />
            <span className="spring-petal two" />
            <span className="spring-petal three" />
            <span className="spring-light" />
            <div className="template-title">春日心动</div>
          </div>
          <div className="template-copy">
            <span>校园恋爱</span>
            <h2>樱花落下之前</h2>
            <p>从新学期的第一声早安开始，在社团、放学路和文化祭里，与喜欢的人慢慢靠近。</p>
            <button className="button primary" type="button" disabled={creating} onClick={() => void createTemplate()}>
              {creating ? "正在创建" : "开始心动"}
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
            <p>还没有保存的故事。就从樱花树下的第一次相遇开始吧。</p>
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
                <p>先给模型清晰的关系、舞台和规则，角色会在游玩中逐渐生长。</p>
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
                      <span>背景与经历</span>
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
