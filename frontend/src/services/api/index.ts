// Re-export everything from all modules

// Client (axios instance and helpers)
export {
  default as api,
  deduplicatedGet,
  debouncedMutation,
  createStreamController,
  abortAllStreams,
  getPendingRequestsCount,
  getActiveStreamsCount,
  API_TIMEOUT,
  MUTATION_DEBOUNCE_MS
} from './client';

// Auth & Users
export {
  login,
  register,
  getCurrentUser,
  refreshToken,
  logoutAllDevices,
  getSessions,
  revokeSession,
  changePassword,
  getUsers,
  createUser,
  deleteUser,
  getHandoverSummary,
  reassignSplit,
  adminResetPassword,
  adminUpdateUser,
  updateUserProfile,
  // Organizations
  getCurrentOrganization,
  getOrgMembers,
  inviteMember,
  updateMemberRole,
  toggleMemberFullAccess,
  removeMember,
  getMyOrgRole,
  // Invitations
  createInvitation,
  getInvitations,
  validateInvitation,
  acceptInvitation,
  revokeInvitation,
  // Departments
  getDepartments,
  getDepartment,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  getDepartmentMembers,
  addDepartmentMember,
  updateDepartmentMember,
  removeDepartmentMember,
  quickAddDepartmentMember,
  getMyDepartments,
  getMyDeptRoles,
  getMyManagedUserIds,
  // Custom Roles
  getCustomRoles,
  getCustomRole,
  createCustomRole,
  updateCustomRole,
  deleteCustomRole,
  setRolePermission,
  removeRolePermission,
  assignCustomRole,
  unassignCustomRole,
  getPermissionAuditLogs,
  // User Permissions
  getMyPermissions,
  getMyMenu,
  getMyFeatures,
  // Sharing
  shareResource,
  revokeShare,
  getMyShares,
  getSharedWithMe,
  getResourceShares,
  getSharableUsers,
  shareChat,
  shareCall,
  shareEntity,
  // Feature Access
  getFeatureSettings,
  setFeatureAccess,
  deleteFeatureSetting,
  getFeatureAuditLogs
} from './auth';

// Auth types
export type {
  PasswordResetResponse,
  AdminUserUpdate,
  UserProfileUpdate,
  OrgRole,
  Organization,
  OrgMember,
  DeptRole,
  InviteMemberRequest,
  Invitation,
  InvitationValidation,
  AcceptInvitationRequest,
  AcceptInvitationResponse,
  Department,
  DepartmentMember,
  CustomRole,
  PermissionOverride,
  PermissionAuditLog,
  EffectivePermissions,
  MenuItem,
  MenuConfig,
  UserFeatures,
  ResourceType,
  AccessLevel,
  ShareRequest,
  ShareResponse,
  UserSimple,
  FeatureSetting,
  FeatureSettingsResponse,
  UserFeaturesResponse,
  SetFeatureAccessRequest,
  FeatureAuditLog
} from './auth';

// Entities
export {
  getEntities,
  getEntity,
  createEntity,
  updateEntity,
  deleteEntity,
  updateEntityStatus,
  linkChatToEntity,
  unlinkChatFromEntity,
  // Red flags
  getEntityRedFlags,
  getEntityRiskScore,
  getEntityStatsByType,
  getEntityStatsByStatus,
  // Smart search
  // Criteria
  getEntityCriteria,
  updateEntityCriteria,
  getEntityDefaultCriteria,
  setEntityDefaultCriteria,
  downloadEntityReport,
  // Similar & duplicates
  getSimilarCandidates,
  getDuplicateCandidates,
  mergeEntities,
  compareCandidates,
  compareCandidatesAI,
  downloadComparisonReport,
  // Files
  getEntityFiles,
  uploadEntityFile,
  deleteEntityFile,
  downloadEntityFile,
  reconvertResume,
  // Parser
  parseResumeFromUrl,
  parseResumeFromFile,
  parseVacancyFromUrl,
  parseVacancyFromFile,
  splitVacancyDescription,
  bulkImportResumes,
  createEntityFromResume,
  // Global search
  globalSearch,
  // AI Profiles
  generateEntityProfile,
  getEntityProfile,
  getSimilarByProfile,
  generateAllProfiles,
  // Background parsing jobs
  startParseJob,
  getParseJobs,
  getParseJob,
  cancelParseJob
} from './entities';

// Entity types
export type {
  OwnershipFilter,
  RedFlag,
  RedFlagsAnalysis,
  RiskScoreResponse,
  EntityDefaultCriteriaResponse,
  SimilarCandidateResult,
  DuplicateCandidateResult,
  MergeEntitiesResponse,
  EntityFile,
  ParsedResume,
  ParsedVacancy,
  BulkImportResult,
  BulkImportResponse,
  CreateEntityFromResumeResponse,
  GlobalSearchCandidate,
  GlobalSearchVacancy,
  GlobalSearchResult,
  GlobalSearchResponse,
  AIProfile,
  ProfileResponse,
  SimilarByProfileResponse,
  BulkProfileResponse,
  ParseJobStatus,
  ParseJob,
  ParseJobsListResponse
} from './entities';

// Chats
export {
  getChats,
  getChat,
  updateChat,
  deleteChat,
  getDeletedChats,
  restoreChat,
  permanentDeleteChat,
  // Messages
  getMessages,
  getParticipants,
  transcribeMessage,
  // Criteria
  getCriteriaPresets,
  createCriteriaPreset,
  updateCriteriaPreset,
  deleteCriteriaPreset,
  getChatCriteria,
  updateChatCriteria,
  getDefaultCriteria,
  setDefaultCriteria,
  resetDefaultCriteria,
  seedUniversalPresets,
  // AI
  getAIHistory,
  clearAIHistory,
  getAnalysisHistory,
  // Stats
  getStats,
  // Streaming
  streamAIMessage,
  streamQuickAction,
  // Reports
  downloadReport,
  // Import
  importTelegramHistory,
  getImportProgress,
  generateImportId,
  cleanupBadImport,
  // Transcription
  transcribeAllMedia,
  repairVideoNotes
} from './chats';

// Chat types
export type {
  DefaultCriteriaResponse,
  StreamOptions,
  ImportResult,
  ImportProgress,
  CleanupResult,
  CleanupMode,
  TranscribeAllResult,
  RepairVideoResult
} from './chats';

// Calls
export {
  getCalls,
  getCall,
  uploadCallRecording,
  uploadTextCall,
  startCallBot,
  getCallStatus,
  stopCallRecording,
  deleteCall,
  linkCallToEntity,
  reprocessCall,
  updateCall,
  // External links
  detectExternalLinkType,
  processExternalURL,
  getExternalProcessingStatus,
  getSupportedExternalTypes,
  // Currency
  getExchangeRates,
  convertCurrencyApi,
  getSupportedCurrencies
} from './calls';

// Call types
export type {
  ExternalLinkType,
  DetectLinkTypeResponse,
  ProcessURLResponse,
  ExchangeRatesResponse,
  CurrencyConversionRequest,
  CurrencyConversionResponse,
  SupportedCurrency,
  SupportedCurrenciesResponse
} from './calls';

// Vacancies
export {
  getVacancies,
  getAllVacancies,
  getVacancy,
  createVacancy,
  updateVacancy,
  deleteVacancy,
  // Applications
  getApplications,
  getFunnelRecruiters,
  createApplication,
  updateApplication,
  deleteApplication,
  // Kanban
  bulkMoveApplications,
  // History
  getApplicationHistory,
  deleteApplicationHistory,
  updateApplicationHistory,
  setPinnedEntry,
  // Stats
  // Entity-Vacancy
  getEntityVacancies,
  // Recommendations
  getRecommendedVacancies,
  autoApplyToVacancy,
  // Assignable users
  getAssignableUsers,
  // Vacancy assignment
  assignVacancy,
  takeVacancy,
  declineVacancy,
  // Recruiter stats
  getVacancyRecruiterStats,
  // AI Scoring
  calculateCompatibilityScore,
  findBestMatchesForVacancy,
  findMatchingVacanciesForEntity,
  getApplicationScore,
  recalculateApplicationScore,
  bulkCalculateScores
} from './vacancies';

// Vacancy types
export type {
  VacancyFilters,
  VacancyCreate,
  VacancyUpdate,
  ApplicationCreate,
  ApplicationUpdate,
  AssignableUser,
  RecruiterStat,
  FunnelRecruiters,
} from './vacancies';



// Interns (Prometheus proxy)
export {
  getPrometheusInterns,
  getPrometheusAnalytics,
  getStudentAchievements,
  getContactPrometheusReview,
  getContactDetailedReview,
  exportInternToContact,
  getInternLinkedContacts,
  syncPrometheusStatuses,
  syncPrometheusStatusSingle,
} from './interns';

// Intern types
export type {
  PrometheusIntern,
  PrometheusTrailSummary,
  PrometheusInternsResponse,
  PrometheusAnalyticsResponse,
  ChurnRisk,
  ChurnRiskStudent,
  FunnelStage,
  TrendPoint,
  ModuleDifficulty,
  AnalyticsSummary,
  TrailProgressItem,
  AnalyticsTopStudent,
  ScoreDistribution,
  DropoffModule,
  DropoffTrail,
  StudentModuleStatus,
  StudentByTrail,
  StudentsByTrailItem,
  AnalyticsTrailFilter,
  AnalyticsFilters,
  StudentAchievementsResponse,
  StudentInfo,
  Achievement,
  AchievementsData,
  SubmissionStats,
  StudentTrailProgress,
  Certificate,
  ContactReviewTrail,
  ContactPrometheusReview,
  ContactPrometheusIntern,
  ContactPrometheusResponse,
  CompetencyScore,
  ProfessionalProfile,
  CompetencyAnalysis,
  TrailInsight,
  TeamFitRecommendation,
  DetailedPrometheusReview,
  DetailedReviewResponse,
  ExportInternResponse,
  LinkedContactsResponse,
  SyncStatusResult,
  SyncStatusesResponse,
  SyncSingleStatusResponse,
} from './interns';

// Notifications
export {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from './notifications';

export type {
  Notification as AppNotification,
  UnreadCountResponse,
} from './notifications';

// Employees
export {
  getEmployees,
  getMyEmployeeProfile,
  getEmployee,
  createEmployee,
  updateEmployee,
  dismissEmployee,
  getLeaveBalance,
  createLeaveRequest,
  getAllLeaveRequests,
  approveLeaveRequest,
  rejectLeaveRequest,
  getEmployeeReminders,
} from './employees';

export type {
  EmployeeData,
  EmployeeCreate,
  EmployeeUpdate,
  LeaveBalance,
  LeaveRequestCreate,
  LeaveRequestData,
  ReminderItem,
} from './employees';

// Documents
export {
  getDocumentTemplates,
  createDocumentTemplate,
  updateDocumentTemplate,
  deleteDocumentTemplate,
  generateDocument,
  getMyDocuments,
  getDocument,
  signDocument,
  getEmployeeDocuments,
} from './documents';

export type {
  DocumentTemplate,
  DocumentTemplateCreate,
  DocumentTemplateUpdate,
  SignedDocument,
  GenerateDocRequest,
  SignDocRequest,
} from './documents';

// Forms
export {
  getMyForms,
  createForm,
  getForm,
  updateForm,
  deleteForm,
  getPublicForm,
  submitPublicForm,
} from './forms';

export type {
  FormField,
  FormTemplate,
  PublicFormData,
  FormCreateData,
  FormUpdateData,
} from './forms';

// Candidate Search CRM
export {
  searchCandidates,
  bulkCandidateAction,
  getCandidateRecruiters,
  getCandidateTags,
} from './candidates';

export type {
  CandidateSearchParams,
  CandidateItem,
  CandidateStats,
  CandidateSearchResult,
  RecruiterOption,
  BulkActionPayload,
  BulkActionResult,
} from './candidates';

// TimeOff
export {
  getTimeOffRequests,
  getTimeOffCalendar,
  approveTimeOff,
  rejectTimeOff,
} from './timeoff';

export type {
  TimeOffRequest,
  TimeOffCalendarEntry,
} from './timeoff';




// Workspaces
export {
  getWorkspaces,
  getWorkspace,
  getWorkspaceCandidates,
} from './workspaces';

export type {
  WorkspaceSummary,
  WorkspaceDetail,
  WorkspaceVacancy,
  WorkspaceCandidate,
  WorkspaceCandidatesResponse,
} from './workspaces';

// Tags
export {
  getTags,
  createTag,
  deleteTag,
  archiveTag,
  restoreTag,
  getEntityTags,
  addTagToEntity,
  removeTagFromEntity,
  getNameTags,
  createNameTag,
  archiveNameTag,
  restoreNameTag,
  getEntityNameTags,
  addNameTagToEntity,
  removeNameTagFromEntity,
} from './tags';

export type {
  Tag,
  TagCreate,
} from './tags';
