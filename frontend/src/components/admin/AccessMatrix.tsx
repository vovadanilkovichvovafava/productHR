import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, X, AlertCircle, Info } from 'lucide-react';
import clsx from 'clsx';

// Role type definition
type Role = 'SUPERADMIN' | 'OWNER' | 'ADMIN' | 'SUB_ADMIN' | 'MEMBER';

// Permission status type
type PermissionStatus = 'allowed' | 'denied' | 'conditional';

// Permission definition with tooltip for conditions
interface Permission {
  id: string;
  label: string;
  description: string;
  permissions: Record<Role, {
    status: PermissionStatus;
    condition?: string; // Explanation for conditional access
  }>;
}

// Permission categories
interface PermissionCategory {
  category: string;
  icon: string;
  permissions: Permission[];
}

// Define the access matrix based on actual backend implementation
const PERMISSIONS_MATRIX: PermissionCategory[] = [
  {
    category: 'Organization',
    icon: '🏢',
    permissions: [
      {
        id: 'view_all_orgs',
        label: 'View All Organizations',
        description: 'Ability to view all organizations in the system',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'denied' },
          ADMIN: { status: 'denied' },
          SUB_ADMIN: { status: 'denied' },
          MEMBER: { status: 'denied' },
        },
      },
      {
        id: 'manage_org_settings',
        label: 'Manage Organization Settings',
        description: 'Edit organization settings and configuration',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: { status: 'denied' },
          SUB_ADMIN: { status: 'denied' },
          MEMBER: { status: 'denied' },
        },
      },
      {
        id: 'invite_users',
        label: 'Invite Users',
        description: 'Send invitations to new users',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: { status: 'allowed' },
          SUB_ADMIN: { status: 'allowed' },
          MEMBER: { status: 'denied' },
        },
      },
    ],
  },
  {
    category: 'Users',
    icon: '👥',
    permissions: [
      {
        id: 'view_users',
        label: 'View Users',
        description: 'View user profiles and information',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: {
            status: 'conditional',
            condition: 'Can view all users in their department + admins from other departments'
          },
          SUB_ADMIN: {
            status: 'conditional',
            condition: 'Can view all users in their department + admins from other departments'
          },
          MEMBER: {
            status: 'conditional',
            condition: 'Can only view users in their own department'
          },
        },
      },
      {
        id: 'delete_users',
        label: 'Delete Users',
        description: 'Remove users from the organization',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: { status: 'denied' },
          SUB_ADMIN: { status: 'denied' },
          MEMBER: { status: 'denied' },
        },
      },
      {
        id: 'change_roles',
        label: 'Change User Roles',
        description: 'Modify user roles and permissions',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: {
            status: 'conditional',
            condition: 'Can only manage roles within their department'
          },
          SUB_ADMIN: { status: 'denied' },
          MEMBER: { status: 'denied' },
        },
      },
    ],
  },
  {
    category: 'Resources',
    icon: '📁',
    permissions: [
      {
        id: 'create_resources',
        label: 'Create Resources',
        description: 'Create chats, contacts, calls, etc.',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: { status: 'allowed' },
          SUB_ADMIN: { status: 'allowed' },
          MEMBER: { status: 'allowed' },
        },
      },
      {
        id: 'share_resources',
        label: 'Share Resources',
        description: 'Share resources with other users',
        permissions: {
          SUPERADMIN: {
            status: 'allowed',
            condition: 'Can share with anyone'
          },
          OWNER: {
            status: 'conditional',
            condition: 'Can share with anyone in their organization'
          },
          ADMIN: {
            status: 'conditional',
            condition: 'Can share within department + with other admins + OWNER/SUPERADMIN'
          },
          SUB_ADMIN: {
            status: 'conditional',
            condition: 'Can share within department + with other admins + OWNER/SUPERADMIN'
          },
          MEMBER: {
            status: 'conditional',
            condition: 'Can only share within their own department'
          },
        },
      },
      {
        id: 'transfer_resources',
        label: 'Transfer Resources',
        description: 'Transfer ownership of resources',
        permissions: {
          SUPERADMIN: {
            status: 'allowed',
            condition: 'Can transfer to anyone'
          },
          OWNER: {
            status: 'allowed',
            condition: 'Can transfer to anyone in organization'
          },
          ADMIN: {
            status: 'conditional',
            condition: 'Can transfer within department or to other admins'
          },
          SUB_ADMIN: {
            status: 'conditional',
            condition: 'Can transfer within department or to other admins'
          },
          MEMBER: {
            status: 'conditional',
            condition: 'Can only transfer within their own department'
          },
        },
      },
      {
        id: 'delete_resources',
        label: 'Delete Resources',
        description: 'Delete chats, contacts, calls, etc.',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: {
            status: 'conditional',
            condition: 'Can delete all org resources except SUPERADMIN private content'
          },
          ADMIN: {
            status: 'conditional',
            condition: 'Can delete resources in their department'
          },
          SUB_ADMIN: {
            status: 'conditional',
            condition: 'Can delete resources in their department'
          },
          MEMBER: {
            status: 'conditional',
            condition: 'Can only delete their own resources'
          },
        },
      },
    ],
  },
  {
    category: 'Departments',
    icon: '🏛️',
    permissions: [
      {
        id: 'create_dept',
        label: 'Create Department',
        description: 'Create new departments',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: { status: 'denied' },
          SUB_ADMIN: { status: 'denied' },
          MEMBER: { status: 'denied' },
        },
      },
      {
        id: 'manage_dept_members',
        label: 'Manage Department Members',
        description: 'Add/remove members from departments',
        permissions: {
          SUPERADMIN: { status: 'allowed' },
          OWNER: { status: 'allowed' },
          ADMIN: {
            status: 'conditional',
            condition: 'Can only manage members in their own department'
          },
          SUB_ADMIN: {
            status: 'conditional',
            condition: 'Can only manage members in their own department'
          },
          MEMBER: { status: 'denied' },
        },
      },
    ],
  },
];

// Role metadata for display
const ROLE_INFO: Record<Role, { name: string; color: string; description: string }> = {
  SUPERADMIN: {
    name: 'Super Admin',
    color: 'text-purple-400',
    description: 'Full system access across all organizations',
  },
  OWNER: {
    name: 'Owner',
    color: 'text-amber-400',
    description: 'Full organization access (except SUPERADMIN private content)',
  },
  ADMIN: {
    name: 'Admin',
    color: 'text-blue-400',
    description: 'Department lead with management permissions',
  },
  SUB_ADMIN: {
    name: 'Sub Admin',
    color: 'text-cyan-400',
    description: 'Department co-lead with similar admin permissions',
  },
  MEMBER: {
    name: 'Member',
    color: 'text-green-400',
    description: 'Regular user with limited department access',
  },
};

// Tooltip component for conditional permissions
interface TooltipProps {
  content: string;
  children: React.ReactNode;
}

function Tooltip({ content, children }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-dark-800 border border-white/10 rounded-lg shadow-xl z-50 w-64 text-xs text-white/90"
        >
          <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 translate-y-1/2 rotate-45 w-2 h-2 bg-dark-800 border-r border-b border-white/10"></div>
          {content}
        </motion.div>
      )}
    </div>
  );
}

// Status cell component
interface StatusCellProps {
  status: PermissionStatus;
  condition?: string;
}

function StatusCell({ status, condition }: StatusCellProps) {
  const icons = {
    allowed: {
      icon: Check,
      color: 'text-green-400',
      bg: 'bg-green-500/10',
      label: 'Allowed',
    },
    denied: {
      icon: X,
      color: 'text-red-400',
      bg: 'bg-red-500/10',
      label: 'Denied',
    },
    conditional: {
      icon: AlertCircle,
      color: 'text-yellow-400',
      bg: 'bg-yellow-500/10',
      label: 'Conditional',
    },
  };

  const config = icons[status];
  const Icon = config.icon;

  const cell = (
    <div className={clsx(
      'flex items-center justify-center p-2 rounded-lg transition-all',
      config.bg,
      condition && 'cursor-help hover:ring-2 hover:ring-white/20'
    )}>
      <Icon className={clsx('w-5 h-5', config.color)} />
    </div>
  );

  if (condition) {
    return <Tooltip content={condition}>{cell}</Tooltip>;
  }

  return cell;
}

// Main component
export default function AccessMatrix() {
  const roles: Role[] = ['SUPERADMIN', 'OWNER', 'ADMIN', 'SUB_ADMIN', 'MEMBER'];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl border border-white/10 overflow-hidden"
    >
      {/* Header */}
      <div className="p-6 border-b border-white/5">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-accent-500/20 rounded-lg">
            <Info className="w-5 h-5 text-accent-400" />
          </div>
          <h2 className="text-2xl font-bold text-white">Access Control Matrix</h2>
        </div>
        <p className="text-dark-300 text-sm ml-11">
          Comprehensive overview of role-based permissions across the system
        </p>
      </div>

      {/* Legend */}
      <div className="px-6 py-4 glass-light border-b border-white/5">
        <div className="flex flex-wrap gap-6 text-sm">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-green-500/10 rounded">
              <Check className="w-4 h-4 text-green-400" />
            </div>
            <span className="text-dark-300">Allowed</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-red-500/10 rounded">
              <X className="w-4 h-4 text-red-400" />
            </div>
            <span className="text-dark-300">Denied</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-yellow-500/10 rounded">
              <AlertCircle className="w-4 h-4 text-yellow-400" />
            </div>
            <span className="text-dark-300">Conditional (hover for details)</span>
          </div>
        </div>
      </div>

      {/* Table - Responsive */}
      <div className="overflow-x-auto">
        <table className="w-full">
          {/* Table Header */}
          <thead className="glass-light sticky top-0 z-10">
            <tr>
              <th className="px-6 py-4 text-left text-sm font-semibold text-white border-b border-white/5">
                Permission
              </th>
              {roles.map((role) => (
                <th
                  key={role}
                  className="px-4 py-4 text-center text-sm font-semibold border-b border-white/5 min-w-[120px]"
                >
                  <Tooltip content={ROLE_INFO[role].description}>
                    <div className={clsx('font-bold', ROLE_INFO[role].color)}>
                      {ROLE_INFO[role].name}
                    </div>
                  </Tooltip>
                </th>
              ))}
            </tr>
          </thead>

          {/* Table Body */}
          <tbody>
            {PERMISSIONS_MATRIX.map((category, categoryIdx) => (
              <React.Fragment key={category.category}>
                {/* Category Header */}
                <tr className="glass-light">
                  <td
                    colSpan={roles.length + 1}
                    className="px-6 py-3 text-sm font-semibold text-white border-b border-white/5"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{category.icon}</span>
                      <span>{category.category}</span>
                    </div>
                  </td>
                </tr>

                {/* Permission Rows */}
                {category.permissions.map((permission, permIdx) => (
                  <motion.tr
                    key={permission.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: categoryIdx * 0.1 + permIdx * 0.05 }}
                    className="hover:bg-dark-800/50 transition-colors"
                  >
                    <td className="px-6 py-4 border-b border-white/5">
                      <Tooltip content={permission.description}>
                        <div>
                          <div className="text-sm font-medium text-white">
                            {permission.label}
                          </div>
                          <div className="text-xs text-dark-400 mt-0.5 line-clamp-1">
                            {permission.description}
                          </div>
                        </div>
                      </Tooltip>
                    </td>
                    {roles.map((role) => (
                      <td
                        key={`${permission.id}-${role}`}
                        className="px-4 py-4 border-b border-white/5"
                      >
                        <StatusCell
                          status={permission.permissions[role].status}
                          condition={permission.permissions[role].condition}
                        />
                      </td>
                    ))}
                  </motion.tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer Note */}
      <div className="px-6 py-4 glass-light border-t border-white/5">
        <p className="text-xs text-dark-400">
          <strong className="text-dark-300">Note:</strong> Hover over role names and conditional
          permissions (yellow icons) to see detailed explanations. This matrix reflects the actual
          implementation in the backend authorization system.
        </p>
      </div>
    </motion.div>
  );
}
