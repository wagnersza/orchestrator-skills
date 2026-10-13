// The tracker interface and its shared types. One backend per tracker (github and gitlab
// now, local later) implements it, and the entry point never calls a tracker CLI itself.

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

// Open issues that carry `label`, and closed ones too where `closed` is set.
export type Filter = { label: string; closed?: boolean };

// A label `install` makes sure the tracker has. `color` is six hex digits, with no `#`.
export type Label = { name: string; color: string; description: string };

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
  // True once a PR that closes `id` is merged, read fresh from the tracker each time.
  isMerged(id: Id): boolean;
  // Squash-merge the open PR that closes `id` and delete its branch. Returns null, or
  // the one reason it refuses and changes nothing: no open PR, a PR that is not
  // mergeable, or a review that requests changes. A merge command that fails throws.
  merge(id: Id): string | null;
  // The shell command a worker runs to read the issue and every comment.
  viewCommand(id: Id): string;
  // The template step that hands the work back for review, with `prSkill` naming the
  // skill that writes the body.
  reviewStep(id: Id, base: string, prSkill: string): string;
  // A parent: an issue with children, or one that carries the user-story label.
  isParent(id: Id): boolean;
  // Every child of `id`, open or closed, read from both forms of the parent link.
  children(id: Id): Id[];
  // Post `body`, then close the issue and drop every state label in one write.
  close(id: Id, body: string): void;
  // Create each label the repo lacks, and leave the others as they are. Returns the
  // names it created.
  ensureLabels(labels: Label[]): string[];
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
// Every state label, one of which an issue in the loop holds.
export const STATES = [READY, IN_PROGRESS, NEEDS_HUMAN, READY_FOR_HUMAN];
