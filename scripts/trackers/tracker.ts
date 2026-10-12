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

// The pull request (or merge request) that closes an issue, as `ref` prints it.
export type Pr = { ref: string; url: string; open: boolean };

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
  // Swap state label `from` for `to` in one write. An issue that already holds `to`
  // gets no write.
  setState(id: Id, from: string, to: string): void;
  comment(id: Id, body: string): void;
  // The open PR that closes `id`, else the newest closed or merged one, else null.
  prFor(id: Id): Pr | null;
  // The shell command a worker runs to read the issue and every comment.
  viewCommand(id: Id): string;
  // The template step that hands the work back for review, with `prSkill` naming the
  // skill that writes the body.
  reviewStep(id: Id, base: string, prSkill: string): string;
  // A parent: an issue with children, or one that carries the user-story label.
  isParent(id: Id): boolean;
  // Every child of `id`, open or closed, read from both forms of the parent link.
  children(id: Id): Id[];
  // Post `body`, then close the issue and drop in-progress in one write.
  close(id: Id, body: string): void;
}

// The state label a human sets to hand an issue to the loop.
export const READY = "ready-for-agent";
// The state label of a claimed issue.
export const IN_PROGRESS = "in-progress";
// The state label of an issue whose worker opened a PR for review.
export const READY_FOR_HUMAN = "ready-for-human";
// The state label of an issue whose worker failed, asked, escalated or died.
export const NEEDS_HUMAN = "needs-human";
// The label that marks a parent, with or without children.
export const USER_STORY = "user-story";
