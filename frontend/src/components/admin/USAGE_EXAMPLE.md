# AccessMatrix Component Usage

## Overview
The `AccessMatrix` component provides a beautiful, interactive table displaying role-based permissions across the system.

## Import

```tsx
import { AccessMatrix } from '@/components/admin';
// or
import AccessMatrix from '@/components/admin/AccessMatrix';
```

## Basic Usage

```tsx
import AccessMatrix from '@/components/admin/AccessMatrix';

function SettingsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">System Permissions</h1>
      <AccessMatrix />
    </div>
  );
}
```

## Usage in Admin Panel

```tsx
import { AccessMatrix } from '@/components/admin';

export default function AdminAccessControlPage() {
  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold bg-gradient-to-r from-accent-400 to-accent-600 bg-clip-text text-transparent">
          Access Control
        </h1>
        <p className="text-dark-300 mt-2">
          Review role-based permissions and access levels
        </p>
      </div>

      <AccessMatrix />
    </div>
  );
}
```

## Features

### Interactive Tooltips
- **Role Names**: Hover over role names in the header to see detailed descriptions
- **Permission Names**: Hover over permission labels to see full descriptions
- **Conditional Access**: Hover over yellow warning icons to see specific conditions

### Visual Indicators
- **Green Checkmark**: Permission is fully allowed
- **Red X**: Permission is denied
- **Yellow Warning**: Conditional access (hover for details)

### Responsive Design
- Mobile-friendly with horizontal scrolling
- Sticky header when scrolling
- Optimized for all screen sizes

## Customization

The component uses Tailwind CSS classes and can be customized by:

1. **Modifying the permission matrix**: Edit the `PERMISSIONS_MATRIX` constant
2. **Changing colors**: Update the `ROLE_INFO` color scheme
3. **Adding new permissions**: Add entries to the appropriate category in `PERMISSIONS_MATRIX`

## Example Integration with Settings Page

```tsx
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AccessMatrix } from '@/components/admin';

export default function SettingsPage() {
  return (
    <div className="p-6">
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          {/* General settings */}
        </TabsContent>

        <TabsContent value="permissions">
          <AccessMatrix />
        </TabsContent>

        <TabsContent value="users">
          {/* User management */}
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

## Permissions Included

### Organization
- View All Organizations
- Manage Organization Settings
- Invite Users

### Users
- View Users
- Delete Users
- Change User Roles

### Resources
- Create Resources
- Share Resources
- Transfer Resources
- Delete Resources

### Departments
- Create Department
- Manage Department Members

## Notes

- The permission matrix reflects the actual backend implementation
- All conditional permissions include detailed explanations via tooltips
- The component is fully typed with TypeScript for better IDE support
