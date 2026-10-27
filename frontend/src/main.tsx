import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider, keepPreviousData } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30 seconds - data is fresh for 30 seconds (prevents flickering)
      refetchOnMount: true, // Refetch on component mount if stale
      refetchOnWindowFocus: false, // Disable to prevent flickering on tab switch
      retry: 1,
      placeholderData: keepPreviousData, // Keep old data while fetching new - prevents blank screen flicker
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: 'var(--toast-bg)',
                color: 'var(--toast-fg)',
                border: '1px solid var(--toast-border)',
              },
            }}
          />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
