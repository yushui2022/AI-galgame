import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api } from "./api";
import { GameView } from "./components/GameView";
import { HomeView } from "./components/HomeView";
import { ProfilePanel } from "./components/ProfilePanel";
import { SetupView } from "./components/SetupView";
import type { Game, ProviderSettings } from "./types";

type View = "loading" | "setup" | "home" | "game";

function gameIdFromPath() {
  return window.location.pathname.match(/^\/games\/([^/]+)$/)?.[1] ?? null;
}

export function App() {
  const [view, setView] = useState<View>("loading");
  const [providers, setProviders] = useState<ProviderSettings | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [activeGameId, setActiveGameId] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const refreshGames = async () => {
    const next = await api.listGames();
    setGames(next);
    return next;
  };

  useEffect(() => {
    let active = true;
    Promise.all([api.getProviders(), api.listGames()])
      .then(([nextProviders, nextGames]) => {
        if (!active) return;
        setProviders(nextProviders);
        setGames(nextGames);
        const ready =
          nextProviders.llm.enabled && nextProviders.image.enabled && nextProviders.video.enabled;
        const requestedGameId = gameIdFromPath();
        const requestedGame = nextGames.find((game) => game.id === requestedGameId);
        if (ready && requestedGame) {
          setActiveGameId(requestedGame.id);
          setView("game");
        } else {
          setView(ready ? "home" : "setup");
        }
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "无法连接后端");
        setView("loading");
      });
    return () => {
      active = false;
    };
  }, []);

  const activeGame = games.find((game) => game.id === activeGameId) ?? null;

  return (
    <main className="app-shell">
      <AnimatePresence mode="wait">
        {view === "loading" && (
          <motion.section
            key="loading"
            className="boot-screen"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="brand-mark">A</div>
            <div>
              <h1>AI Galgame</h1>
              <p>{error ?? "正在唤醒故事引擎"}</p>
            </div>
          </motion.section>
        )}

        {view === "setup" && providers && (
          <SetupView
            key="setup"
            initial={providers}
            onComplete={(saved) => {
              setProviders(saved);
              setView("home");
            }}
          />
        )}

        {view === "home" && (
          <HomeView
            key="home"
            games={games}
            onOpenSettings={() => setView("setup")}
            onOpenProfile={() => setProfileOpen(true)}
            onOpenGame={(id) => {
              window.history.pushState({}, "", `/games/${id}`);
              setActiveGameId(id);
              setView("game");
            }}
            onCreated={async (game) => {
              await refreshGames();
              window.history.pushState({}, "", `/games/${game.id}`);
              setActiveGameId(game.id);
              setView("game");
            }}
          />
        )}

        {view === "game" && activeGame && (
          <GameView
            key={activeGame.id}
            game={activeGame}
            onBack={async () => {
              await refreshGames();
              window.history.pushState({}, "", "/");
              setView("home");
            }}
            onGameChanged={async () => {
              const next = await refreshGames();
              const refreshed = next.find((game) => game.id === activeGame.id);
              if (!refreshed) setView("home");
            }}
            onOpenProfile={() => setProfileOpen(true)}
          />
        )}
      </AnimatePresence>

      <ProfilePanel open={profileOpen} onClose={() => setProfileOpen(false)} />
    </main>
  );
}
