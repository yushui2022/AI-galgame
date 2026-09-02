import { useEffect, useState } from "react";
import {
  FloppyDisk as FloppyDiskIcon,
  Trash as TrashIcon,
  UserFocus as UserFocusIcon,
  X as XIcon
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api } from "../api";
import type { PlayerProfile } from "../types";

interface ProfilePanelProps {
  open: boolean;
  onClose: () => void;
}

function tagsToText(tags: string[]) {
  return tags.join("、");
}

function textToTags(value: string) {
  return value
    .split(/[、,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProfilePanel({ open, onClose }: ProfilePanelProps) {
  const [profile, setProfile] = useState<PlayerProfile | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    let active = true;
    api.getProfile().then((result) => {
      if (active) setProfile(result);
    });
    return () => {
      active = false;
    };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
          <motion.aside
            className="profile-drawer"
            initial={reduceMotion ? false : { x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div className="drawer-title">
                <UserFocusIcon size={26} weight="duotone" />
                <div>
                  <h2>玩家画像</h2>
                  <p>这些偏好会影响后续剧情和选项。</p>
                </div>
              </div>
              <button className="icon-button" type="button" onClick={onClose} aria-label="关闭">
                <XIcon size={20} />
              </button>
            </header>

            {!profile ? (
              <div className="drawer-loading">正在读取画像</div>
            ) : (
              <div className="profile-form">
                <label>
                  <span>偏好主题</span>
                  <input
                    value={tagsToText(profile.preferred_themes)}
                    onChange={(event) => setProfile({ ...profile, preferred_themes: textToTags(event.target.value) })}
                    placeholder="慢热、日常、治愈"
                  />
                </label>
                <label>
                  <span>角色特质</span>
                  <input
                    value={tagsToText(profile.preferred_character_traits)}
                    onChange={(event) =>
                      setProfile({ ...profile, preferred_character_traits: textToTags(event.target.value) })
                    }
                    placeholder="克制、聪明、温柔"
                  />
                </label>
                <label>
                  <span>剧情节奏</span>
                  <select value={profile.pacing} onChange={(event) => setProfile({ ...profile, pacing: event.target.value })}>
                    <option>舒缓</option>
                    <option>均衡</option>
                    <option>紧凑</option>
                  </select>
                </label>
                <label>
                  <span>给系统的备注</span>
                  <textarea rows={5} value={profile.notes} onChange={(event) => setProfile({ ...profile, notes: event.target.value })} />
                </label>

                <div className="profile-observed">
                  <h3>已观察到的倾向</h3>
                  <div className="observed-grid">
                    {Object.entries(profile.choice_tendencies).length === 0 ? (
                      <p>继续游玩后，这里会出现你的选择倾向。</p>
                    ) : (
                      Object.entries(profile.choice_tendencies).map(([tag, value]) => (
                        <span key={tag}>{tag} {value.toFixed(1)}</span>
                      ))
                    )}
                  </div>
                  <p>完整观看 {profile.watched_videos} 次，跳过 {profile.skipped_videos} 次</p>
                </div>

                <div className="drawer-actions">
                  <button
                    className="button secondary danger"
                    type="button"
                    onClick={() =>
                      void api.resetProfile().then((result) => {
                        setProfile(result);
                        setMessage("画像已重置");
                      })
                    }
                  >
                    <TrashIcon size={18} />
                    重置
                  </button>
                  <button
                    className="button primary"
                    type="button"
                    onClick={() =>
                      void api.saveProfile(profile).then((result) => {
                        setProfile(result);
                        setMessage("画像已保存");
                      })
                    }
                  >
                    <FloppyDiskIcon size={18} />
                    保存画像
                  </button>
                </div>
                {message && <p className="inline-message">{message}</p>}
              </div>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
