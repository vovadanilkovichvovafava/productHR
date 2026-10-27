import axios, { AxiosError, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import toast from 'react-hot-toast';

// ============================================================
// CSRF TOKEN MANAGEMENT
// ============================================================

/**
 * Get CSRF token from cookie (set by backend)
 */
const getCSRFToken = (): string | null => {
  const name = 'csrf_token=';
  const decodedCookie = decodeURIComponent(document.cookie);
  const cookies = decodedCookie.split(';');
  for (const cookie of cookies) {
    const trimmed = cookie.trim();
    if (trimmed.indexOf(name) === 0) {
      return trimmed.substring(name.length);
    }
  }
  return null;
};

// ============================================================
// REFRESH TOKEN MANAGEMENT
// ============================================================

/**
 * Flag to indicate if a token refresh is currently in progress
 */
let isRefreshing = false;

/**
 * Queue of requests waiting for token refresh to complete
 */
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
  config: InternalAxiosRequestConfig;
}> = [];

/**
 * Process the queue of failed requests after token refresh
 */
const processQueue = (error: Error | null): void => {
  failedQueue.forEach(({ resolve, reject, config }) => {
    if (error) {
      reject(error);
    } else {
      // Retry the request
      resolve(api(config));
    }
  });
  failedQueue = [];
};

/**
 * Silently attempt to refresh the access token
 * Returns true if successful, false otherwise
 *
 * Экспортируется для ПРОАКТИВНОГО рефреша (WebSocketProvider): access-токен живёт
 * 15 мин, и без упреждающего обновления каждые ~15 мин наступало окно, где WS
 * ловил 403, а API — 401 (до реактивного рефреша на поллинге), и юзера «выкидывало».
 */
export const attemptTokenRefresh = async (): Promise<boolean> => {
  try {
    const response = await axios.post('/api/auth/refresh', {}, {
      withCredentials: true, // Send cookies
    });
    return response.status === 200;
  } catch {
    return false;
  }
};

/**
 * Redirect to login page (used after refresh token failure)
 */
const redirectToLogin = (): void => {
  // Clear any stored state before redirecting.
  // Public, no-auth pages (login, invite, candidate form links) must never be
  // bounced to /login by a background 401.
  //
  // Mini App — отдельный случай: он авторизуется подписью Telegram и живёт
  // внутри мессенджера, где страницы входа сайта просто нет. Без этого
  // исключения любой фоновый 401 подменял приложение формой «Войдите в
  // систему» от веб-версии, и человек упирался в запрос пароля, которого у
  // него в Telegram быть не должно.
  if (
    window.location.pathname !== '/login' &&
    !window.location.pathname.startsWith('/invite') &&
    !window.location.pathname.startsWith('/form/') &&
    !window.location.pathname.startsWith('/miniapp')
  ) {
    window.location.href = '/login';
  }
};

// API Configuration
export const API_TIMEOUT = 30000; // 30 seconds
export const MUTATION_DEBOUNCE_MS = 300; // Debounce time for mutation requests

// ============================================================
// REQUEST DEDUPLICATION & DEBOUNCE SYSTEM
// ============================================================

/**
 * Map to store pending GET requests for deduplication
 * Key: method + url + serialized params
 * Value: Promise of the request
 */
const pendingRequests = new Map<string, Promise<AxiosResponse>>();

/**
 * Map to store active AbortControllers for streaming requests
 * Key: unique request identifier
 * Value: AbortController instance
 */
const activeStreamControllers = new Map<string, AbortController>();

/**
 * Map to track last mutation timestamps for debouncing
 * Key: method + url
 * Value: timestamp of last mutation
 */
const mutationTimestamps = new Map<string, number>();

/**
 * Generate a unique key for request deduplication
 */
const generateRequestKey = (
  method: string,
  url: string,
  params?: Record<string, unknown>
): string => {
  const sortedParams = params ? JSON.stringify(params, Object.keys(params).sort()) : '';
  return `${method.toUpperCase()}:${url}:${sortedParams}`;
};

/**
 * Check if a mutation request should be debounced (prevent double-click)
 * Returns true if the request should proceed, false if it should be blocked
 */
const shouldAllowMutation = (method: string, url: string): boolean => {
  const key = `${method.toUpperCase()}:${url}`;
  const now = Date.now();
  const lastTimestamp = mutationTimestamps.get(key);

  if (lastTimestamp && now - lastTimestamp < MUTATION_DEBOUNCE_MS) {
    console.warn(`Mutation debounced: ${method.toUpperCase()} ${url} (too fast, ${now - lastTimestamp}ms since last request)`);
    return false;
  }

  mutationTimestamps.set(key, now);
  return true;
};

/**
 * Cleanup old mutation timestamps periodically (prevent memory leaks)
 */
const cleanupMutationTimestamps = () => {
  const now = Date.now();
  const staleThreshold = 60000; // 1 minute

  mutationTimestamps.forEach((timestamp, key) => {
    if (now - timestamp > staleThreshold) {
      mutationTimestamps.delete(key);
    }
  });
};

// Run cleanup every 5 minutes
setInterval(cleanupMutationTimestamps, 300000);

/**
 * Wrapper for GET requests with deduplication
 * If the same request is already in flight, returns the existing Promise
 */
export const deduplicatedGet = async <T>(
  url: string,
  config?: AxiosRequestConfig
): Promise<AxiosResponse<T>> => {
  const requestKey = generateRequestKey('GET', url, config?.params);

  // Check if identical request is already in flight
  const pendingRequest = pendingRequests.get(requestKey);
  if (pendingRequest) {
    console.debug(`Request deduplicated: GET ${url}`);
    return pendingRequest as Promise<AxiosResponse<T>>;
  }

  // Create new request and store it
  const requestPromise = api.get<T>(url, config);
  pendingRequests.set(requestKey, requestPromise as Promise<AxiosResponse>);

  try {
    const response = await requestPromise;
    return response;
  } finally {
    // Remove from pending requests after completion (success or error)
    pendingRequests.delete(requestKey);
  }
};

/**
 * Wrapper for mutation requests with debounce protection
 * Throws error if request is too fast (double-click protection)
 */
export const debouncedMutation = async <T>(
  method: 'post' | 'put' | 'patch' | 'delete',
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<AxiosResponse<T>> => {
  if (!shouldAllowMutation(method, url)) {
    throw new Error('Request debounced: too many rapid requests');
  }

  switch (method) {
    case 'post':
      return api.post<T>(url, data, config);
    case 'put':
      return api.put<T>(url, data, config);
    case 'patch':
      return api.patch<T>(url, data, config);
    case 'delete':
      return api.delete<T>(url, config);
    default:
      throw new Error(`Unknown method: ${method}`);
  }
};

/**
 * Create an AbortController for a streaming request
 * Returns the controller and a cleanup function
 */
export const createStreamController = (streamId: string): {
  controller: AbortController;
  cleanup: () => void;
} => {
  // Abort any existing stream with the same ID
  const existingController = activeStreamControllers.get(streamId);
  if (existingController) {
    existingController.abort();
    activeStreamControllers.delete(streamId);
  }

  const controller = new AbortController();
  activeStreamControllers.set(streamId, controller);

  const cleanup = () => {
    controller.abort();
    activeStreamControllers.delete(streamId);
  };

  return { controller, cleanup };
};

/**
 * Abort all active streaming requests (useful for cleanup)
 */
export const abortAllStreams = (): void => {
  activeStreamControllers.forEach((controller, streamId) => {
    console.debug(`Aborting stream: ${streamId}`);
    controller.abort();
  });
  activeStreamControllers.clear();
};

/**
 * Get the count of pending requests (for debugging/monitoring)
 */
export const getPendingRequestsCount = (): number => pendingRequests.size;

/**
 * Get the count of active streams (for debugging/monitoring)
 */
export const getActiveStreamsCount = (): number => activeStreamControllers.size;

// ============================================================
// «НАБЛЮДАТЕЛЬ» (is_readonly) — ЗАПРЕТ ЗАПИСИ НА КЛИЕНТЕ
// ============================================================

/**
 * Наблюдатель (ментор): видит весь HR, но ничего не меняет. Сервер режет любой
 * не-GET (403 «Режим Наблюдатель…»), но тихий 403 на КЛИЕНТЕ выглядел как
 * «кнопка сломалась»: комментарий отправлялся в никуда, этап «менялся» и
 * возвращался после F5 (жалоба владельца 01.10.2026). Поэтому запись
 * останавливаем до запроса — одним понятным сообщением.
 *
 * Список доменов, где наблюдатель ПИШЕТ как обычный сотрудник (Практика,
 * проекты, свои уведомления), повторяет `_ro_writable_prefixes` в
 * backend/api/services/auth.py — расходиться им нельзя.
 */
let observerMode = false;

export const setObserverMode = (on: boolean): void => {
  observerMode = on;
};

export const OBSERVER_WRITABLE_PREFIXES = [
  '/auth/',            // выход, рефреш, свой пароль
  '/chats',
  '/calls',
  '/interns',
  '/criteria',
  '/projects',
  '/project-statuses',
  '/timeoff',
  '/blockers',
  '/notifications',
] as const;

/** Сообщение, которое видит наблюдатель вместо молчаливого 403. */
export const OBSERVER_BLOCK_MESSAGE =
  'Режим наблюдателя — только просмотр, изменения запрещены';

export const isObserverBlocked = (method?: string, url?: string): boolean => {
  if (!observerMode) return false;
  const verb = (method || 'get').toUpperCase();
  if (verb === 'GET' || verb === 'HEAD' || verb === 'OPTIONS') return false;
  // url приходит и абсолютным, и относительным (baseURL = /api) — приводим к
  // одному виду, иначе префиксы не совпадут.
  const path = (url || '')
    .replace(/^https?:\/\/[^/]+/, '')
    .replace(/[?#].*$/, '')
    .replace(/^\/api(?=\/)/, '');
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return !OBSERVER_WRITABLE_PREFIXES.some((prefix) => normalized.startsWith(prefix));
};

// Когда человек последний раз что-то нажимал. Нужно, чтобы отличить КЛИК от
// фонового запроса: наблюдателю сыпались плашки на ровном месте — карточка при
// открытии сама просит проверку дублей, а это запись (замечание владельца
// 01.10.2026). На фоновое молчим, на нажатое — объясняем, иначе получится
// «нажал, ничего не произошло».
let lastGestureAt = 0;
if (typeof document !== 'undefined') {
  const mark = () => { lastGestureAt = Date.now(); };
  document.addEventListener('pointerdown', mark, true);
  document.addEventListener('keydown', mark, true);
}

let lastObserverToast = 0;

const rejectObserverWrite = (): Error => {
  const now = Date.now();
  const byUser = now - lastGestureAt < 2000;
  // Один тост на серию: одно нажатие может дёрнуть несколько запросов.
  if (byUser && now - lastObserverToast > 1500) {
    lastObserverToast = now;
    toast.error(OBSERVER_BLOCK_MESSAGE);
  }
  const error = new Error(OBSERVER_BLOCK_MESSAGE);
  (error as Error & { isObserverBlock?: boolean }).isObserverBlock = true;
  return error;
};

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,  // Send cookies with requests (httpOnly cookie authentication)
  timeout: API_TIMEOUT,   // Request timeout
});

// Request interceptor - add CSRF token and retry metadata
api.interceptors.request.use(
  (config) => {
    // Наблюдатель: до сети. См. isObserverBlocked.
    if (isObserverBlocked(config.method, config.url)) {
      return Promise.reject(rejectObserverWrite());
    }

    // Add request timestamp for debugging
    (config as AxiosRequestConfig & { metadata?: { startTime: number } }).metadata = { startTime: Date.now() };

    // Add CSRF token for state-changing requests (POST, PUT, PATCH, DELETE)
    const method = config.method?.toUpperCase();
    if (method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrfToken = getCSRFToken();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
      }
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle errors with automatic token refresh
api.interceptors.response.use(
  (response) => {
    // Log slow requests in development
    const config = response.config as AxiosRequestConfig & { metadata?: { startTime: number } };
    if (config.metadata?.startTime) {
      const duration = Date.now() - config.metadata.startTime;
      if (duration > 5000) {
        console.warn(`Slow API request: ${config.method?.toUpperCase()} ${config.url} took ${duration}ms`);
      }
    }
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _skipRefresh?: boolean };

    // «Наблюдатель» (read-only): сервер режет любой не-GET у такого юзера (403 с
    // detail про «Наблюдатель»). Отклоняем ТИХО — у наблюдателя постоянный баннер
    // сверху и отключённые кнопки, поэтому назойливый тост на каждое действие не нужен.
    if (error.response?.status === 403) {
      const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
      if (typeof detail === 'string' && detail.includes('Наблюдатель')) {
        return Promise.reject(error);
      }
    }

    // Handle 401 - Unauthorized (token expired or invalid)
    if (error.response?.status === 401) {
      // Skip refresh logic for certain endpoints
      const skipRefreshUrls = ['/auth/login', '/auth/refresh', '/auth/logout', '/invitations/validate', '/invitations/accept'];
      const shouldSkipRefresh = originalRequest._skipRefresh ||
        skipRefreshUrls.some(url => originalRequest.url?.includes(url));

      // Skip refresh if on login/invite page
      const isAuthPage = window.location.pathname === '/login' || window.location.pathname.startsWith('/invite');

      if (shouldSkipRefresh || isAuthPage) {
        return Promise.reject(error);
      }

      // If this request has already been retried, redirect to login
      if (originalRequest._retry) {
        redirectToLogin();
        return Promise.reject(error);
      }

      // If already refreshing, queue this request
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject, config: originalRequest });
        });
      }

      // Mark that we're refreshing
      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Attempt to refresh the token (silently, no error shown to user)
        const refreshSuccess = await attemptTokenRefresh();

        if (refreshSuccess) {
          // Token refreshed successfully, process queued requests and retry original
          processQueue(null);
          return api(originalRequest);
        } else {
          // Refresh failed - redirect to login
          processQueue(new Error('Token refresh failed'));
          redirectToLogin();
          return Promise.reject(error);
        }
      } catch (refreshError) {
        // Refresh threw an error - redirect to login
        processQueue(refreshError instanceof Error ? refreshError : new Error('Token refresh failed'));
        redirectToLogin();
        return Promise.reject(error);
      } finally {
        isRefreshing = false;
      }
    }

    // Handle 403 - permission denied
    if (error.response?.status === 403) {
      console.error('Permission denied:', error.config?.url);
    }

    // Handle timeout
    if (error.code === 'ECONNABORTED') {
      console.error('Request timeout:', error.config?.url);
    }

    return Promise.reject(error);
  }
);

export default api;
