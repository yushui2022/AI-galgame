import { useState } from "react";
import {
  ArrowRight as ArrowRightIcon,
  ArrowUpRight as ArrowUpRightIcon,
  BookOpenText as BookOpenTextIcon,
  FilmSlate as FilmSlateIcon,
  GearSix as GearSixIcon,
  ImageSquare as ImageSquareIcon,
  Play as PlayIcon,
  Plus as PlusIcon,
  Sparkle as SparkleIcon,
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
      className="library-page library-premium"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <header className="topbar library-topbar">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <div>
            <span>AI Galgame</span>
            <small>GENERATIVE STORY SYSTEM</small>
          </div>
        </div>
        <nav>
          <span className="engine-online"><i />故事引擎就绪</span>
          <button className="library-nav-button" type="button" onClick={onOpenProfile} aria-label="玩家画像">
            <UserFocusIcon size={22} />
            <span>偏好</span>
          </button>
          <button className="library-nav-button" type="button" onClick={onOpenSettings} aria-label="模型设置">
            <GearSixIcon size={22} />
            <span>模型</span>
          </button>
        </nav>
      </header>

      <section className="library-hero" aria-labelledby="library-title">
        <img
          className="library-hero-image"
          src="/images/romance-library-hero.png"
          alt="春日校园门口，抱着摄影集的少女站在樱花树下"
        />
        <div className="library-hero-scrim" />
        <div className="library-hero-copy">
          <p className="eyebrow">Generative visual novel</p>
          <h1 id="library-title" aria-label="故事会记住你的选择。">故事会记住<br aria-hidden="true" />你的选择。</h1>
          <p>剧情、关系与镜头都在你做出决定后继续生长。没有预设路线，也不需要等待整章生成。</p>
          <div className="library-hero-actions">
            <button className="button primary hero-primary" type="button" disabled={creating} onClick={() => void createTemplate()}>
              <PlayIcon size={18} weight="fill" />
              {creating ? "正在创建" : "开始心动"}
            </button>
            <button className="hero-text-action" type="button" onClick={() => setCustomOpen(true)}>
              从一个想法开始
              <ArrowUpRightIcon size={18} />
            </button>
          </div>
          <div className="engine-capabilities" aria-label="故事引擎能力">
            <span><SparkleIcon size={17} />实时续写</span>
            <span><ImageSquareIcon size={17} />场景生成</span>
            <span><FilmSlateIcon size={17} />动态镜头</span>
          </div>
        </div>
        <div className="featured-story-label">
          <span>推荐开场 · 01</span>
          <strong>樱花落下之前</strong>
          <small>校园恋爱 / 春日 / 慢热</small>
        </div>
      </section>

      <section className="saved-section premium-shelf">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Your library</p>
            <h2>继续你的故事</h2>
          </div>
          <span>{games.length} 个存档</span>
        </div>
        <div className="story-shelf-grid">
          {games.length === 0 ? (
            <div className="empty-state premium-empty">
              <BookOpenTextIcon size={32} weight="light" />
              <div>
                <strong>还没有正在生长的故事</strong>
                <p>从上面的推荐开场开始，第一段记忆会自动保存在这里。</p>
              </div>
            </div>
          ) : (
            games.map((game, index) => (
              <button key={game.id} className="story-card" type="button" onClick={() => onOpenGame(game.id)}>
                <div className="story-card-media">
                  <img
                    src={index % 2 === 0 ? "/images/romance-library-hero.png" : "/images/romance-custom-rooftop.png"}
                    alt=""
                    aria-hidden="true"
                  />
                  <span>{game.genre}</span>
                  <ArrowUpRightIcon size={20} />
                </div>
                <div className="story-card-copy">
                  <strong>{game.title}</strong>
                  <p>{game.premise}</p>
                  <div>
                    <span>{game.branches.filter((branch) => !branch.archived).length} 条故事线</span>
                    <span>继续游玩 <ArrowRightIcon size={15} /></span>
                  </div>
                </div>
              </button>
            ))
          )}

          <button className="story-card create-story-card" type="button" onClick={() => setCustomOpen(true)}>
            <div className="story-card-media">
              <img src="/images/romance-custom-rooftop.png" alt="" aria-hidden="true" />
              <span>自由创作</span>
              <PlusIcon size={21} />
            </div>
            <div className="story-card-copy">
              <strong>从一个念头开始</strong>
              <p>定义题材、角色与画面风格，让 Agent 为你组织接下来发生的一切。</p>
              <div><span>创建新故事</span><span>开始设置 <ArrowRightIcon size={15} /></span></div>
            </div>
          </button>
        </div>
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
