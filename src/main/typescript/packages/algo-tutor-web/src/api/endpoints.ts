// One function per SPEC §15 endpoint, typed with the generated contract.
// Return types follow the API's routes (packages/algo_tutor/api/routes_*).
import { api, newIdempotencyKey } from './client';

import type {
  AttemptOut,
  AttemptStart,
  BackupStatus,
  BankStatus,
  BundledSet,
  Desk,
  DispositionIn,
  DraftPatch,
  FinishIn,
  FinishOut,
  HintConversation,
  HintReply,
  Language,
  ListCreated,
  ListDetail,
  ListEntriesIn,
  ListPatch,
  ListPreview,
  ListSummary,
  MistakeList,
  Notebook,
  NotebookPatch,
  PackReport,
  PatternDetail,
  PatternSummary,
  PlanOut,
  ProblemCreate,
  ProblemDetail,
  ProblemPage,
  ProblemPatch,
  ProblemQuery,
  ReflectionPatch,
  ReorderIn,
  Report,
  ReviewPatch,
  ReviewTargetOut,
  SettingsOut,
  SettingsPatch,
  SetupIn,
  SetupState,
  SignalsPatch,
  SuggestedPath,
  TimerIn,
  TopicDetail,
  TopicLevels,
  TutorStatus,
  TutorTest,
} from './types';

const enc = encodeURIComponent;

// ------------------------------------------------------------ setup, settings

export const getSetup = () => api.get<SetupState>('/setup');
export const postSetup = (body: SetupIn) =>
  api.post<SetupState>('/setup', body);

export const getSettings = () => api.get<SettingsOut>('/settings');
export const patchSettings = (body: SettingsPatch) =>
  api.patch<SettingsOut>('/settings', body);

// ------------------------------------------------------------ desk and plans

export const getDesk = () => api.get<Desk>('/desk');
// Every plan write returns the plan; the desk refetches anyway. All of them
// are 403 HIDDEN_ASSESSMENT during an assessment, and rebuild only takes
// today's plan.
export const ensureToday = () => api.post<PlanOut>('/plans/today/ensure');
export const rebuildPlan = (
  planId: string,
  version: number,
  idempotencyKey = newIdempotencyKey(),
) =>
  api.post<PlanOut>(
    `/plans/${enc(planId)}/rebuild`,
    { version },
    { idempotencyKey },
  );
export const activateItem = (planId: string, itemId: string, version: number) =>
  api.post<PlanOut>(`/plans/${enc(planId)}/items/${enc(itemId)}/activate`, {
    version,
  });
export const reorderLane = (planId: string, body: ReorderIn) =>
  api.post<PlanOut>(`/plans/${enc(planId)}/reorder`, body);
export const disposeItem = (
  planId: string,
  itemId: string,
  body: DispositionIn,
) =>
  api.post<PlanOut>(
    `/plans/${enc(planId)}/items/${enc(itemId)}/disposition`,
    body,
  );

// ------------------------------------------------------------ problems

export type ProblemFilters = Partial<ProblemQuery>;

export const getProblems = (query: ProblemFilters) =>
  api.get<ProblemPage>('/problems', { query });
// 201 when new, 200 with the existing problem.
export const createProblem = (body: ProblemCreate) =>
  api.post<ProblemDetail>('/problems', body);
export const getProblem = (id: string) =>
  api.get<ProblemDetail>(`/problems/${enc(id)}`);
export const patchProblem = (id: string, body: ProblemPatch) =>
  api.patch<ProblemDetail>(`/problems/${enc(id)}`, body);
export const getSuggestedPath = (id: string, language: Language) =>
  api.get<SuggestedPath>(`/problems/${enc(id)}/suggested-path`, {
    query: { language },
  });
export const patchReview = (problemId: string, body: ReviewPatch) =>
  api.patch<ReviewTargetOut>(`/reviews/${enc(problemId)}`, body);

// ------------------------------------------------------------ attempts

export const startAttempt = (body: AttemptStart) =>
  api.post<AttemptOut>('/attempts', body);
export const getAttempt = (id: string) =>
  api.get<AttemptOut>(`/attempts/${enc(id)}`);
export const patchDraft = (id: string, body: DraftPatch) =>
  api.patch<AttemptOut>(`/attempts/${enc(id)}/draft`, body);
export const postTimer = (id: string, body: TimerIn) =>
  api.post<AttemptOut>(`/attempts/${enc(id)}/timer`, body);
export const finishAttempt = (
  id: string,
  body: FinishIn,
  idempotencyKey: string,
) =>
  api.post<FinishOut>(`/attempts/${enc(id)}/finish`, body, { idempotencyKey });
// 204, no body.
export const cancelAttempt = (id: string) => api.delete(`/attempts/${enc(id)}`);
export const patchReflection = (id: string, body: ReflectionPatch) =>
  api.patch<AttemptOut>(`/attempts/${enc(id)}/reflection`, body);
// Reflection, signals and report are 422 VALIDATION until the attempt is
// completed; the report is 503 TUTOR_UNAVAILABLE (kind disabled) with the
// tutor off.
export const patchSignals = (id: string, body: SignalsPatch) =>
  api.patch<AttemptOut>(`/attempts/${enc(id)}/signals`, body);
export const requestReport = (id: string) =>
  api.post<Report>(`/attempts/${enc(id)}/report`);
export const getHints = (id: string) =>
  api.get<HintConversation>(`/attempts/${enc(id)}/hints`);
export const postHint = (id: string, text: string) =>
  api.post<HintReply>(`/attempts/${enc(id)}/hints`, { text });

// ------------------------------------------------------------ lists and packs

export const getLists = () => api.get<ListSummary[]>('/lists');
export const previewList = (body: ListEntriesIn) =>
  api.post<ListPreview>('/lists/preview', body);
export const createList = (body: ListEntriesIn) =>
  api.post<ListCreated>('/lists', body);
export const getList = (id: string) => api.get<ListDetail>(`/lists/${enc(id)}`);
// `unresolved` lists the lines of `add_text` that matched nothing.
export const patchList = (id: string, body: ListPatch) =>
  api.patch<ListDetail>(`/lists/${enc(id)}`, body);
// 204, no body.
export const deleteList = (id: string) => api.delete(`/lists/${enc(id)}`);
// 201 the first time, 200 with the existing list after that.
export const followBundled = (set: BundledSet) =>
  api.post<ListDetail>(`/lists/bundled/${enc(set)}`);
export const activateList = (id: string) =>
  api.post<ListSummary>(`/lists/${enc(id)}/activate`);
export const deactivateList = (id: string) =>
  api.post<ListSummary>(`/lists/${enc(id)}/deactivate`);
// The body is the question pack itself (SPEC §5.9).
export const importPack = (
  pack: unknown,
  dryRun: boolean,
  idempotencyKey: string,
) =>
  api.post<PackReport>('/packs', pack, {
    query: { dry_run: dryRun },
    idempotencyKey,
  });

// ------------------------------------------------------------ bank

export const getBank = () => api.get<BankStatus>('/bank');
export const refreshBank = () => api.post<BankStatus>('/bank/refresh');

// ------------------------------------------------------------ notebooks

export const getTopics = () => api.get<TopicLevels>('/topics');
export const getTopic = (id: string) =>
  api.get<TopicDetail>(`/topics/${enc(id)}`);
export const patchTopicNotebook = (id: string, body: NotebookPatch) =>
  api.patch<Notebook>(`/topics/${enc(id)}/notebook`, body);
export const getPatterns = () => api.get<PatternSummary[]>('/patterns');
export const getPattern = (id: string) =>
  api.get<PatternDetail>(`/patterns/${enc(id)}`);
export const patchPatternNotebook = (id: string, body: NotebookPatch) =>
  api.patch<Notebook>(`/patterns/${enc(id)}/notebook`, body);
export const getMistakes = () => api.get<MistakeList>('/mistakes');

// ------------------------------------------------------------ tutor, backups

export const getTutorStatus = () => api.get<TutorStatus>('/tutor/status');
export const testTutor = () => api.post<TutorTest>('/tutor/test');
export const getBackup = () => api.get<BackupStatus>('/backup');
export const postBackup = () => api.post<BackupStatus>('/backup');
