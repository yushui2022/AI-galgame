export interface ProviderConfig {
  kind: string;
  base_url: string;
  api_key: string;
  model: string;
  enabled: boolean;
  extra: Record<string, unknown>;
}
export interface ProviderSettings {
  llm: ProviderConfig;
  image: ProviderConfig;
  video: ProviderConfig;
  embedding: ProviderConfig | null;
}

export interface CharacterInput {
  name: string;
  role: string;
  personality: string;
  appearance: string;
  background: string;
}

export interface Character extends CharacterInput {
  id: string;
  reference_image_url: string | null;
}

export interface Branch {
  id: string;
  name: string;
  head_turn_id: string | null;
  archived: boolean;
  created_at: string;
}

export interface Game {
  id: string;
  title: string;
  genre: string;
  premise: string;
  world_rules: string;
  art_style: string;
  safety_level: string;
  status: string;
  created_at: string;
  characters: Character[];
  branches: Branch[];
}

export interface Choice {
  id: string;
  text: string;
  tags: string[];
}

export interface Dialogue {
  speaker: string;
  text: string;
  emotion: string;
}

export interface MediaAsset {
  id: string;
  kind: "image" | "video";
  provider: string;
  url: string | null;
  size_bytes: number;
}

export interface Turn {
  id: string;
  game_id: string;
  parent_turn_id: string | null;
  turn_index: number;
  player_input_type: string;
  player_action: string;
  scene: string;
  narrative: string;
  dialogue: Dialogue[];
  choices: Choice[];
  media_status: string;
  unlocked: boolean;
  media_assets: MediaAsset[];
  created_at: string;
}

export interface PlayerProfile {
  preferred_themes: string[];
  preferred_character_traits: string[];
  pacing: string;
  choice_tendencies: Record<string, number>;
  character_affinities: Record<string, number>;
  watched_videos: number;
  skipped_videos: number;
  notes: string;
}

export interface GameCreatePayload {
  mode: "template" | "custom";
  title: string;
  genre: string;
  premise: string;
  world_rules: string;
  art_style: string;
  characters: CharacterInput[];
}
