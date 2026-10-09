// State contract for the kb-actions mod. The engine validates every $.state key
// the hooks module names against this interface.

export type KbSnapshot = {
  /** Experience entry files, experiences/*.md (archive/ excluded). */
  experiences: number;
  /** `## ` headings in knowledge/learnings.md. */
  learnings: number;
  /** Days since INDEX.md "Last verified", null when missing or unparsable. */
  verifiedDays: number | null;
  /** Days since INDEX.md "Last synthesized", null when missing or unparsable. */
  synthesizedDays: number | null;
  /** Modified files in the KB git repo, from git status --porcelain. */
  dirtyFiles: number;
  /** Experience entry files modified after this session began. */
  sessionEntries: number;
  /** True when the KB root was found with experiences/ and knowledge/. */
  present: boolean;
};

declare module 'claude-code' {
  interface PluginState {
    'andrei-personal': {
      /** Latest KB snapshot. */
      snapshot: KbSnapshot | null;
      /** Pending experience-debt lines from ~/.claude/kb-session/experience-debt. */
      pendingDebt: string[];
      /** Tool uses counted this session, main loop only. */
      toolUses: number;
    };
  }
}
