import type {
  Branch,
  Game,
  GameCreatePayload,
  PlayerProfile,
  ProviderSettings,
  Turn
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    }
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, payload.detail ?? "请求失败");
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  getProviders: () => request<ProviderSettings>("/api/settings/providers"),
  saveProviders: (payload: ProviderSettings) =>
    request<ProviderSettings>("/api/settings/providers", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  testProvider: (category: "llm" | "image" | "video" | "embedding") =>
    request<{ ok: boolean; message: string; latency_ms: number }>(
      `/api/settings/providers/${category}/test`,
      { method: "POST" }
    ),
  listGames: () => request<Game[]>("/api/games"),
  createGame: (payload: GameCreatePayload) =>
    request<Game>("/api/games", { method: "POST", body: JSON.stringify(payload) }),
  getGame: (id: string) => request<Game>(`/api/games/${id}`),
  generateCharacterReferences: (id: string) =>
    request<Game>(`/api/games/${id}/characters/generate`, { method: "POST" }),
  getBranches: (gameId: string) => request<Branch[]>(`/api/games/${gameId}/branches`),
  getTurns: (branchId: string) => request<Turn[]>(`/api/branches/${branchId}/turns`),
  submitTurn: (
    branchId: string,
    payload: {
      input_type: "suggested" | "free_text";
      text: string;
      choice_id?: string;
      expected_head_turn_id: string;
    }
  ) =>
    request<{ turn: Turn; job_id: string }>(`/api/branches/${branchId}/turns`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  forkBranch: (branchId: string, turnId: string, name?: string) =>
    request<Branch>(`/api/branches/${branchId}/fork`, {
      method: "POST",
      body: JSON.stringify({ turn_id: turnId, name })
    }),
  renameBranch: (branchId: string, name: string) =>
    request<Branch>(`/api/branches/${branchId}`, {
      method: "PUT",
      body: JSON.stringify({ name })
    }),
  archiveBranch: (branchId: string) =>
    request<Branch>(`/api/branches/${branchId}`, { method: "DELETE" }),
  restoreBranch: (branchId: string) =>
    request<Branch>(`/api/branches/${branchId}/restore`, { method: "POST" }),
  purgeBranch: (branchId: string) =>
    request<{ ok: boolean; deleted_turns: number; deleted_media: number }>(
      `/api/branches/${branchId}/purge?confirm=true`,
      { method: "DELETE" }
    ),
  retryMedia: (turnId: string) =>
    request<{ job_id: string }>(`/api/turns/${turnId}/media/retry`, { method: "POST" }),
  skipMedia: (turnId: string) =>
    request<{ ok: boolean }>(`/api/turns/${turnId}/media/skip`, { method: "POST" }),
  completeMedia: (turnId: string) =>
    request<{ ok: boolean }>(`/api/turns/${turnId}/media/complete`, { method: "POST" }),
  getProfile: () => request<PlayerProfile>("/api/player-profile"),
  saveProfile: (payload: PlayerProfile) =>
    request<PlayerProfile>("/api/player-profile", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  resetProfile: () => request<PlayerProfile>("/api/player-profile", { method: "DELETE" }),
  uploadReference: (gameId: string, characterId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<Game>(`/api/games/${gameId}/characters/${characterId}/reference`, {
      method: "POST",
      body: data
    });
  }
};
