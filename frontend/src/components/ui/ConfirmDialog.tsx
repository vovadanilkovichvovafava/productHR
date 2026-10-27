import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Info, AlertCircle, X } from 'lucide-react';
import clsx from 'clsx';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

const variantConfig = {
  danger: {
    icon: AlertCircle,
    iconColor: 'text-red-400',
    bgColor: 'bg-red-500/10',
    buttonColor: 'bg-red-600 hover:bg-red-500',
  },
  warning: {
    icon: AlertTriangle,
    iconColor: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
    buttonColor: 'bg-yellow-600 hover:bg-yellow-500',
  },
  info: {
    icon: Info,
    iconColor: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    buttonColor: 'bg-blue-600 hover:bg-blue-500',
  },
};

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  onCancel,
  loading = false,
}: ConfirmDialogProps) {
  const config = variantConfig[variant];
  const Icon = config.icon;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && !loading) {
      onCancel();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onKeyDown={handleKeyDown}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          aria-describedby="confirm-dialog-description"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            onClick={loading ? undefined : onCancel}
          />
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="relative w-full max-w-md bg-[#1a1a2e]/98 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-start gap-4 p-6 pb-4">
              <div className={clsx('p-2 rounded-xl', config.bgColor)}>
                <Icon className={clsx('w-6 h-6', config.iconColor)} aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <h3
                  id="confirm-dialog-title"
                  className="text-lg font-bold text-white"
                >
                  {title}
                </h3>
                <p id="confirm-dialog-description" className="mt-2 text-sm text-white/50">{message}</p>
              </div>
              <button
                onClick={onCancel}
                disabled={loading}
                className="p-2 text-white/30 hover:text-white hover:bg-white/10 rounded-xl transition-colors disabled:opacity-50"
                aria-label="Close dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 p-6 pt-4 border-t border-white/5">
              <button
                type="button"
                onClick={onCancel}
                disabled={loading}
                className="px-4 py-2 text-sm text-white/50 hover:text-white hover:bg-white/5 rounded-xl transition-colors disabled:opacity-50"
              >
                {cancelLabel}
              </button>
              <button
                type="button"
                onClick={onConfirm}
                disabled={loading}
                className={clsx(
                  'px-5 py-2.5 text-sm font-medium text-white rounded-xl transition-colors disabled:opacity-50',
                  config.buttonColor
                )}
              >
                {loading ? 'Processing...' : confirmLabel}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
