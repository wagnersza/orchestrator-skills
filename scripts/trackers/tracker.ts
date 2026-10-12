// The tracker interface and its shared types. One backend per tracker (github now,
// gitlab and local later) implements it, and the entry point never calls a tracker CLI
// itself.

// An issue id as the backend names it: "349" on GitHub, "owner/repo#12" for an issue in
// another repo, "<feature>/NN" on the local tracker.
export type Id = string;

export type Issue = {
  id: Id;
  title: string;
  open: boolean;
  labels: string[];
  assignees: string[];
  body: string;
};

// Open issues that carry `label`.
export type Filter = { label: string };

export interface Tracker {
  list(filter: Filter): Issue[];
  view(id: Id): Issue;
  // The login the tracker knows the person running the orchestrator by.
  me(): string;
  // Every issue that blocks `id`, open or closed.
  blockers(id: Id): Id[];
  // How a line printed for a human names the issue, such as "#349".
  ref(id: Id): string;
  // Assign me, add in-progress and remove ready-for-agent, in one write.
  claim(id: Id): void;
  // Undo a claim whose worker did not start, in one write.
  unclaim(id: Id): void;
  // The shell command a worker runs to read the issue and every comment.
  viewCommand(id: Id): string;
  // The template step that hands the work back for review, with `prSkill` naming the
  // skill that writes the body.
  reviewStep(id: Id, base: string, prSkill: string): string;
}

// The state label a human sets to hand an issue to the loop.
export const READY = "ready-for-agent";
// The state label of a claimed issue.
export const IN_PROGRESS = "in-progress";
