// Types mirror backend/app/schemas/**. Keep field names identical to the
// Pydantic models — this file is the frontend's contract with the API.

export type UserRole = "ADMIN" | "PROJECT_MANAGER" | "SITE_SUPERVISOR";

export type ProjectStatus =
  | "PLANNING"
  | "ACTIVE"
  | "ON_HOLD"
  | "COMPLETED"
  | "CANCELLED";

export type ActivityStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "SUSPENDED";

export type WBSLevel = "L1" | "L2" | "L3" | "L4" | "L5" | "L6";

export type MatchStatus =
  | "AUTO_MATCHED"
  | "NEEDS_REVIEW"
  | "UNMATCHED"
  | "MANUALLY_CONFIRMED"
  | "MANUALLY_REJECTED";

export type MatchMethod =
  | "EXACT_ID"
  | "EXACT_CODE"
  | "KEYWORD"
  | "FUZZY"
  | "SEMANTIC"
  | "HYBRID"
  | "MANUAL";

export type Discipline =
  | "CIVIL"
  | "PIPING"
  | "ELECTRICAL"
  | "MECHANICAL"
  | "INSTRUMENTATION"
  | "STRUCTURAL"
  | "WELDING_NDT"
  | "SURVEY"
  | "COATING"
  | "TESTING_PRECOMMISSIONING"
  | "OTHER";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type PredictionMethod =
  | "RULE_BASED_RATE"
  | "RANDOM_FOREST"
  | "NOT_FORECASTABLE";

export type DocumentType =
  | "SCHEDULE"
  | "DAILY_PROGRESS_REPORT"
  | "SITE_DIARY"
  | "DISCIPLINE_SHEET"
  | "OTHER";

export type GeneratedReportFormat = "PDF" | "XLSX";
export type GeneratedReportStatus =
  | "PENDING"
  | "GENERATING"
  | "COMPLETED"
  | "FAILED";
export type JobStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
export type NotificationChannel = "IN_APP" | "EMAIL" | "WHATSAPP" | "VAPI";
export type NotificationStatus =
  | "PENDING"
  | "SENT"
  | "DELIVERED"
  | "READ"
  | "FAILED";
export type DependencyType = "FS" | "SS" | "FF" | "SF";

export interface ErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}
export interface ErrorEnvelope {
  error: ErrorDetail;
}

export interface Page<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

// ---------------------------------------------------------------- auth/user
export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginResponse extends TokenPair {
  user: UserRead;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name: string;
  phone?: string | null;
}

export interface UserAdminCreate extends UserCreate {
  role: UserRole;
}

export interface UserUpdate {
  full_name?: string;
  phone?: string | null;
}

export interface PasswordChange {
  password: string;
  current_password: string;
}

// -------------------------------------------------------------- project
export interface ProjectRead {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  client_name: string | null;
  location: string | null;
  planned_start: string | null;
  planned_finish: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectWithRole extends ProjectRead {
  my_role: UserRole;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  client_name?: string | null;
  location?: string | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  code: string;
  status?: ProjectStatus;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  status?: ProjectStatus;
  client_name?: string | null;
  location?: string | null;
  planned_start?: string | null;
  planned_finish?: string | null;
}

export interface MemberDetail {
  id: string;
  project_id: string;
  user_id: string;
  role: UserRole;
  created_at: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

export interface MemberAdd {
  user_id?: string | null;
  email?: string | null;
  role: UserRole;
}

export interface MemberRoleUpdatePayload {
  role: UserRole;
}

export interface MemberRead {
  id: string;
  project_id: string;
  user_id: string;
  role: UserRole;
  created_at: string;
}

// -------------------------------------------------------------- schedule
export interface ScheduleRead {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  uploaded_by_id: string | null;
  status: JobStatus;
  parse_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ScheduleColumnMapping {
  activity_code: string;
  name: string;
  wbs_path?: string | null;
  level?: string | null;
  discipline?: string | null;
  planned_start?: string | null;
  planned_finish?: string | null;
  budgeted_quantity?: string | null;
  uom?: string | null;
  predecessors?: string | null;
}

export interface ActivityDependencyRead {
  id: string;
  predecessor_id: string;
  successor_id: string;
  dependency_type: DependencyType;
  lag: number;
}

export interface ActivityRead {
  id: string;
  schedule_id: string;
  activity_code: string;
  name: string;
  wbs_path: string;
  level: number;
  discipline: Discipline | null;
  planned_start: string | null;
  planned_finish: string | null;
  budgeted_quantity: number | null;
  uom: string | null;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityWithDependencies extends ActivityRead {
  predecessors: ActivityDependencyRead[];
  successors: ActivityDependencyRead[];
}

export interface ActivityTreeNode extends ActivityRead {
  children: ActivityTreeNode[];
}

// -------------------------------------------------------------- progress
export interface ActualProgressCreate {
  reporting_date: string;
  actual_quantity?: number | null;
  percent_complete?: number | null;
  actual_start?: string | null;
  actual_finish?: string | null;
  status: ActivityStatus;
  notes?: string | null;
  source_report_id?: string | null;
}

export interface ActualProgressRead extends ActualProgressCreate {
  id: string;
  activity_id: string;
  reported_by_id: string | null;
}

export interface ActivityProgressRollup {
  activity_id: string;
  activity_code: string;
  name: string;
  wbs_path: string;
  level: number;
  completion_percentage: number;
  status: ActivityStatus;
  is_delayed: boolean;
  is_leaf: boolean;
  weight: number;
}

export interface MatchApplicationSummary {
  schedule_id: string;
  matches_considered: number;
  records_created: number;
  records_updated: number;
  skipped_not_an_actual_event: number;
  skipped_missing_event_date: number;
  skipped_other_schedule: number;
}

// -------------------------------------------------------------- matching
export interface ExtractedActivityRead {
  id: string;
  project_id: string;
  progress_report_id: string;
  source_ref: string;
  raw_text: string;
  event_type: string;
  activity_code: string | null;
  discipline: string | null;
  event_date: string | null;
  percent_complete: number | null;
  quantity: number | null;
  uom: string | null;
  chainage_from_m: number | null;
  chainage_to_m: number | null;
  joint_from: number | null;
  joint_to: number | null;
  extraction_confidence: number;
  extractor: string;
  created_at: string;
}

export interface MatchCandidateRead {
  activity_id: string;
  activity_code: string;
  activity_name: string;
  wbs_path: string;
  level: number;
  score: number;
  method: string;
  signals: Record<string, number>;
  explanation: string[];
}

export interface ActivityMatchRead {
  id: string;
  project_id: string;
  extracted_activity_id: string;
  activity_id: string | null;
  status: MatchStatus;
  auto_status: string;
  method: string;
  score: number;
  reason: string | null;
  signals: Record<string, unknown>;
  candidates: MatchCandidateRead[];
  embedding_provider: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
}

export interface ActivityMatchDetail extends ActivityMatchRead {
  extracted: ExtractedActivityRead;
}

export interface MatchRunRequest {
  progress_report_id?: string | null;
  schedule_id?: string | null;
  auto_threshold?: number | null;
  review_threshold?: number | null;
  reprocess?: boolean;
}

export interface MatchRunSummary {
  reports_processed: number;
  items_extracted: number;
  matches_created: number;
  auto_matched: number;
  needs_review: number;
  unmatched: number;
  schedule_id: string | null;
  extractors_used: string[];
  embedding_provider: string;
  llm_available: boolean;
  auto_threshold: number;
  review_threshold: number;
}

export interface MatchReviewDecision {
  decision: "confirm" | "reject" | "reassign";
  activity_id?: string | null;
  note?: string | null;
}

export interface MatchStatsRead {
  total: number;
  auto_matched: number;
  needs_review: number;
  unmatched: number;
  manually_confirmed: number;
  manually_rejected: number;
  auto_precision: number | null;
  reviewed_count: number;
}

export interface AuditEntryRead {
  action: string;
  actor_user_id: string | null;
  created_at: string;
  details: Record<string, unknown>;
}

// -------------------------------------------------------------- prediction
export interface TrainRequest {
  schedule_id?: string | null;
}

export interface ModelMetrics {
  roc_auc: number | null;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  brier: number | null;
}

export interface TrainingOutcome {
  trained: boolean;
  reason: string | null;
  detail: string;
  labelled_activities: number;
  late_samples: number;
  on_time_samples: number;
  version: string | null;
  kind: string | null;
  train_samples: number | null;
  test_samples: number | null;
  metrics: ModelMetrics | null;
  baseline_roc_auc: number | null;
  feature_importances: Array<Record<string, unknown>> | null;
}

export interface ModelVersionRead {
  id: string;
  version: string;
  kind: string;
  is_active: boolean;
  trained_at: string;
  training_samples: number;
  late_samples: number;
  on_time_samples: number;
  train_samples: number;
  test_samples: number;
  roc_auc: number | null;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  brier: number | null;
  baseline_roc_auc: number | null;
  feature_importances: Array<Record<string, unknown>>;
  hyperparameters: Record<string, unknown>;
}

export interface PredictRequest {
  as_of?: string | null;
  force_rule_based?: boolean;
}

export interface PredictionRunSummary {
  schedule_id: string;
  as_of: string;
  method: PredictionMethod;
  model_version: string | null;
  model_note: string;
  activities_scored: number;
  not_forecastable: number;
  by_risk_level: Record<string, number>;
}

export interface PredictionRead {
  id: string;
  activity_id: string;
  method: PredictionMethod;
  probability: number;
  predicted_late: boolean;
  risk_level: RiskLevel;
  planned_finish: string | null;
  forecast_finish: string | null;
  forecast_slip_days: number | null;
  as_of: string;
}

export interface PredictionDetail extends PredictionRead {
  activity_code: string | null;
  activity_name: string | null;
  wbs_path: string | null;
  model_version: string | null;
  explanation: Record<string, unknown>;
  caveats: string[];
  features: Record<string, unknown>;
}

export interface RiskBucket {
  risk_level: RiskLevel;
  count: number;
}

export interface RiskSummary {
  schedule_id: string;
  as_of: string | null;
  method: PredictionMethod | null;
  model_version: string | null;
  total_predictions: number;
  predicted_late: number;
  by_risk_level: RiskBucket[];
  worst_forecast_slip_days: number | null;
  top_risks: PredictionDetail[];
  note: string;
}

// -------------------------------------------------------------- analytics
export interface SCurvePoint {
  reporting_date: string;
  planned_percentage: number;
  actual_percentage: number | null;
}

export interface AnalyticsSummary {
  as_of: string;
  total_activities: number;
  leaf_activities: number;
  completed_activities: number;
  delayed_activities: number;
  overall_completion_percentage: number;
  planned_completion_percentage: number | null;
  schedule_variance: number | null;
  activities_with_progress: number;
  last_reported_on: string | null;
}

// -------------------------------------------------------------- documents
export interface UploadedFileRead {
  id: string;
  project_id: string;
  uploaded_by_id: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  document_type: DocumentType;
  created_at: string;
  updated_at: string;
}

export interface ProcessingJobRead {
  id: string;
  project_id: string;
  uploaded_file_id: string;
  status: JobStatus;
  processor: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadAccepted {
  file: UploadedFileRead;
  job: ProcessingJobRead;
}

export interface ProgressReportRead {
  id: string;
  project_id: string;
  uploaded_file_id: string;
  report_date: string | null;
  discipline: Discipline | null;
  raw_text: string;
  extracted_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// -------------------------------------------------------------- reporting
export interface GeneratedReportCreate {
  report_type: string;
  output_format: GeneratedReportFormat;
  as_of?: string | null;
  parameters?: Record<string, unknown>;
}

export interface GeneratedReportRead {
  id: string;
  project_id: string;
  requested_by_id: string | null;
  report_type: string;
  output_format: GeneratedReportFormat;
  status: GeneratedReportStatus;
  parameters: Record<string, unknown>;
  snapshot: Record<string, unknown>;
  filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  error_message: string | null;
  generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationRead {
  id: string;
  project_id: string | null;
  recipient_user_id: string | null;
  channel: NotificationChannel;
  status: NotificationStatus;
  notification_type: string;
  event_key: string | null;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  attempt_count: number;
  last_error: string | null;
  scheduled_for: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationCreate {
  project_id?: string | null;
  recipient_user_id?: string | null;
  channel: NotificationChannel;
  notification_type: string;
  title: string;
  body: string;
  recipient_address?: string | null;
  event_key?: string | null;
  idempotency_key?: string | null;
  payload?: Record<string, unknown>;
  scheduled_for?: string | null;
}

export interface HealthResponse {
  status: string;
  environment: string;
  version: string;
}

export interface ReadinessResponse {
  status: string;
  database: string;
  checks_passed: boolean;
}
