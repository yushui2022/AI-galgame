import { useMemo, useState } from "react";
import {
  ArrowRight as ArrowRightIcon,
  CheckCircle as CheckCircleIcon,
  FilmSlate as FilmSlateIcon,
  Image as ImageIcon,
  Key as KeyIcon,
  Sparkle as SparkleIcon,
  WarningCircle as WarningCircleIcon
} from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { api } from "../api";
import type { ProviderConfig, ProviderSettings } from "../types";

interface SetupViewProps {
  initial: ProviderSettings;
  onComplete: (settings: ProviderSettings) => void;
}

type Category = "llm" | "image" | "video";

const META: Record<
  Category,
  { title: string; description: string; icon: typeof SparkleIcon; kinds: { value: string; label: string }[] }
> = {
  llm: {
    title: "剧情模型",
    description: "负责导演、编剧、角色审核与记忆整理。支持 MiniCPM 等 OpenAI-compatible 接口。",
    icon: SparkleIcon,
    kinds: [
      { value: "minicpm", label: "MiniCPM / OpenAI-compatible" },
      { value: "openai", label: "其他 OpenAI-compatible" }
    ]
  },
  image: {
    title: "图片模型",
    description: "每回合先生成16:9场景图，同时作为视频的首帧。",
    icon: ImageIcon,
    kinds: [
      { value: "ark", label: "火山方舟 / Seedream" },
      { value: "minimax", label: "MiniMax Image" },
      { value: "openai", label: "OpenAI Images-compatible" }
    ]
  },
  video: {
    title: "视频模型",
    description: "把本回合场景图转成约6秒连续镜头。",
    icon: FilmSlateIcon,
    kinds: [
      { value: "seedance", label: "火山方舟 / Seedance" },
      { value: "minimax", label: "MiniMax Hailuo" }
    ]
  }
};

function defaults(category: Category, kind: string): Pick<ProviderConfig, "base_url" | "model"> {
  if (category === "image" && kind === "ark") {
    return { base_url: "https://ark.cn-beijing.volces.com/api/v3", model: "" };
  }
  if (category === "image" && kind === "minimax") {
    return { base_url: "https://api.minimax.cn", model: "image-01" };
  }
  if (category === "video" && kind === "minimax") {
    return { base_url: "https://api.minimax.cn", model: "MiniMax-Hailuo-2.3-Fast" };
  }
  if (category === "video" && kind === "seedance") {
    return { base_url: "https://ark.cn-beijing.volces.com/api/v3", model: "" };
  }
  return { base_url: "", model: category === "llm" ? "MiniCPM" : "" };
}

export function SetupView({ initial, onComplete }: SetupViewProps) {
  const [settings, setSettings] = useState<ProviderSettings>(initial);
  const [active, setActive] = useState<Category>("llm");
  const [tests, setTests] = useState<Partial<Record<Category, "testing" | "ok" | "error">>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [embeddingTest, setEmbeddingTest] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const reduceMotion = useReducedMotion();

  const allPassed = useMemo(
    () => (Object.keys(META) as Category[]).every((category) => tests[category] === "ok"),
    [tests]
  );

  const update = (category: Category, patch: Partial<ProviderConfig>) => {
    setSettings((current) => ({
      ...current,
      [category]: { ...current[category], ...patch }
    }));
  };

  const copyArkCredentials = (target: "image" | "video") => {
    const source = target === "image" ? settings.video : settings.image;
    const targetKind = target === "image" ? "ark" : "seedance";
    setSettings((current) => ({
      ...current,
      [target]: {
        ...current[target],
        kind: targetKind,
        base_url: source.base_url || "https://ark.cn-beijing.volces.com/api/v3",
        api_key: source.api_key
      }
    }));
    setTests((current) => ({ ...current, [target]: undefined }));
    setMessage(
      `已把方舟地址和 API Key 复制到${target === "image" ? "图片" : "视频"}配置；模型 ID 需要单独填写。`
    );
  };

  const persistAndTest = async (category: Category) => {
    setMessage(null);
    setTests((current) => ({ ...current, [category]: "testing" }));
    try {
      const saved = await api.saveProviders({
        ...settings,
        [category]: { ...settings[category], enabled: true }
      });
      setSettings(saved);
      const result = await api.testProvider(category);
      setTests((current) => ({ ...current, [category]: "ok" }));
      setMessage(`${META[category].title}：${result.message}`);
    } catch (reason) {
      setTests((current) => ({ ...current, [category]: "error" }));
      setMessage(reason instanceof Error ? reason.message : "测试失败");
    }
  };

  const finish = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveProviders({
        ...settings,
        llm: { ...settings.llm, enabled: true },
        image: { ...settings.image, enabled: true },
        video: { ...settings.video, enabled: true }
      });
      onComplete(saved);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const config = settings[active];
  const ActiveIcon = META[active].icon;
  const embedding = settings.embedding;

  const toggleEmbedding = (enabled: boolean) => {
    setSettings((current) => ({
      ...current,
      embedding: enabled
        ? current.embedding ?? {
            kind: "openai",
            base_url: current.llm.base_url,
            api_key: current.llm.api_key,
            model: "",
            enabled: true,
            extra: {}
          }
        : null
    }));
    setEmbeddingTest("idle");
  };

  const updateEmbedding = (patch: Partial<ProviderConfig>) => {
    setSettings((current) => ({
      ...current,
      embedding: current.embedding ? { ...current.embedding, ...patch } : null
    }));
    setEmbeddingTest("idle");
  };

  const testEmbedding = async () => {
    if (!settings.embedding) return;
    setEmbeddingTest("testing");
    setMessage(null);
    try {
      const saved = await api.saveProviders(settings);
      setSettings(saved);
      const result = await api.testProvider("embedding");
      setEmbeddingTest("ok");
      setMessage(`语义记忆：${result.message}`);
    } catch (reason) {
      setEmbeddingTest("error");
      setMessage(reason instanceof Error ? reason.message : "Embeddings 测试失败");
    }
  };

  return (
    <motion.section
      className="setup-layout"
      initial={reduceMotion ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
    >
      <aside className="setup-aside">
        <div className="brand-lockup">
          <div className="brand-mark">A</div>
          <span>AI Galgame</span>
        </div>
        <div className="setup-copy">
          <p className="eyebrow">第一次启动</p>
          <h1>把你的模型接入故事。</h1>
          <p>所有密钥只保存在这台电脑的后端数据目录，不会进入浏览器存储或 Git。</p>
        </div>
        <div className="privacy-note">
          <KeyIcon size={22} weight="duotone" />
          <span>本地保存，接口响应始终脱敏</span>
        </div>
      </aside>

      <div className="setup-main">
        <nav className="setup-tabs" aria-label="供应商配置">
          {(Object.keys(META) as Category[]).map((category) => {
            const Icon = META[category].icon;
            return (
              <button
                key={category}
                className={active === category ? "setup-tab active" : "setup-tab"}
                onClick={() => setActive(category)}
                type="button"
              >
                <Icon size={20} />
                <span>{META[category].title}</span>
                {tests[category] === "ok" && <CheckCircleIcon className="tab-state success" weight="fill" />}
                {tests[category] === "error" && <WarningCircleIcon className="tab-state error" weight="fill" />}
              </button>
            );
          })}
        </nav>

        <div className="provider-form">
          <div className="form-heading">
            <ActiveIcon size={30} weight="duotone" />
            <div>
              <h2>{META[active].title}</h2>
              <p>{META[active].description}</p>
            </div>
          </div>

          <label>
            <span>供应商</span>
            <select
              value={config.kind}
              onChange={(event) => {
                const kind = event.target.value;
                update(active, { kind, ...defaults(active, kind) });
              }}
            >
              {META[active].kinds.map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>API 地址</span>
            <input
              value={config.base_url}
              onChange={(event) => update(active, { base_url: event.target.value })}
              placeholder="https://..."
              autoComplete="url"
            />
          </label>

          <label>
            <span>模型或 Endpoint ID</span>
            <input
              value={config.model}
              onChange={(event) => update(active, { model: event.target.value })}
              placeholder={active === "video" ? "填写当前可用的视频模型 ID" : "模型名称"}
              autoComplete="off"
            />
          </label>

          <label>
            <span>API Key</span>
            <input
              type="password"
              value={config.api_key}
              onChange={(event) => update(active, { api_key: event.target.value })}
              placeholder="只保存在本机"
              autoComplete="new-password"
            />
          </label>

          {active === "image" && config.kind === "ark" && (
            <div className="provider-hint">
              <div>
                <strong>方舟媒体凭证可以共用</strong>
                <span>复用视频配置的地址和 API Key；Seedream 图片模型 ID 仍单独填写。</span>
              </div>
              <button className="button ghost" type="button" onClick={() => copyArkCredentials("image")}>
                从视频配置复制
              </button>
            </div>
          )}

          {active === "video" && config.kind === "seedance" && (
            <div className="provider-hint">
              <div>
                <strong>方舟媒体凭证可以共用</strong>
                <span>复用图片配置的地址和 API Key；Seedance 视频模型 ID 仍单独填写。</span>
              </div>
              <button className="button ghost" type="button" onClick={() => copyArkCredentials("video")}>
                从图片配置复制
              </button>
            </div>
          )}

          {active === "llm" && (
            <details className="embedding-settings">
              <summary>
                <span>可选：语义记忆 Embeddings</span>
                <small>未启用时使用内置 SQLite FTS5</small>
              </summary>
              <label className="switch-row">
                <input
                  type="checkbox"
                  checked={Boolean(embedding)}
                  onChange={(event) => toggleEmbedding(event.target.checked)}
                />
                <span>启用 OpenAI-compatible 向量检索</span>
              </label>
              {embedding && (
                <div className="embedding-fields">
                  <label>
                    <span>API 地址</span>
                    <input value={embedding.base_url} onChange={(event) => updateEmbedding({ base_url: event.target.value })} />
                  </label>
                  <label>
                    <span>模型</span>
                    <input value={embedding.model} onChange={(event) => updateEmbedding({ model: event.target.value })} />
                  </label>
                  <label>
                    <span>API Key</span>
                    <input type="password" value={embedding.api_key} onChange={(event) => updateEmbedding({ api_key: event.target.value })} />
                  </label>
                  <button
                    className="button ghost"
                    type="button"
                    disabled={embeddingTest === "testing"}
                    onClick={() => void testEmbedding()}
                  >
                    {embeddingTest === "testing" ? "正在检查" : embeddingTest === "ok" ? "语义记忆已连接" : "测试语义记忆"}
                  </button>
                </div>
              )}
            </details>
          )}

          <div className="form-actions">
            <button
              className="button secondary"
              type="button"
              disabled={tests[active] === "testing"}
              onClick={() => void persistAndTest(active)}
            >
              {tests[active] === "testing" ? "正在检查" : "保存并测试"}
            </button>
            <button className="button primary" type="button" disabled={!allPassed || saving} onClick={() => void finish()}>
              {saving ? "正在进入" : "进入故事库"}
              <ArrowRightIcon size={18} />
            </button>
          </div>

          {message && <p className={tests[active] === "error" || embeddingTest === "error" ? "inline-message error" : "inline-message"}>{message}</p>}
        </div>
      </div>
    </motion.section>
  );
}
