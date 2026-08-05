# Frontend Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Start Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Prerequisites

- Node.js 18+ (20.x recommended)
- npm or yarn
- Backend API running on port 8000

## Backend Connection

The frontend expects the backend to be running at `http://localhost:8000`. Start the backend first:

```bash
# In the project-foundation directory
cd ../
uvicorn app.main:app --reload
```

## Project Structure

```
frontend/
├── src/
│   ├── app/                      # Next.js App Router pages
│   │   ├── layout.tsx            # Root layout with sidebar & nav
│   │   ├── page.tsx              # Dashboard (/)
│   │   ├── projects/
│   │   │   ├── page.tsx          # Projects list
│   │   │   └── [id]/page.tsx    # Project details
│   │   ├── runs/
│   │   │   ├── page.tsx          # Runs list
│   │   │   └── [id]/page.tsx    # Run details with timeline
│   │   ├── artifacts/page.tsx   # Artifacts (placeholder)
│   │   ├── review/page.tsx      # Human review (placeholder)
│   │   └── settings/page.tsx    # Settings
│   │
│   ├── components/
│   │   ├── ui/                   # Base UI components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── input.tsx
│   │   │   ├── label.tsx
│   │   │   └── skeleton.tsx
│   │   ├── layout/               # Layout components
│   │   │   ├── sidebar.tsx
│   │   │   └── top-navigation.tsx
│   │   ├── providers/            # Context providers
│   │   │   ├── theme-provider.tsx
│   │   │   └── query-provider.tsx
│   │   ├── status-badge.tsx      # Status indicators
│   │   ├── empty-state.tsx       # Empty state component
│   │   ├── page-header.tsx       # Page header
│   │   ├── theme-toggle.tsx      # Theme switcher
│   │   └── workflow-timeline.tsx # Workflow visualization
│   │
│   ├── hooks/
│   │   └── use-api.ts            # React Query hooks
│   │
│   ├── lib/
│   │   ├── utils.ts              # Utility functions
│   │   └── api-client.ts         # API client
│   │
│   ├── services/
│   │   └── api.service.ts        # API service layer
│   │
│   └── types/
│       └── api.ts                # TypeScript types
│
├── public/                        # Static assets
├── .env.local                     # Environment variables
├── next.config.ts                 # Next.js configuration
├── tailwind.config.ts             # Tailwind CSS config
├── tsconfig.json                  # TypeScript config
└── package.json                   # Dependencies
```

## Architecture

### API Layer

```typescript
// lib/api-client.ts - Base HTTP client
apiClient.get('/api/v1/projects')

// services/api.service.ts - Feature services
projectsService.getAll()
runsService.getById(id)

// hooks/use-api.ts - React Query hooks
useProjects()
useRun(id)
```

### State Management

- **TanStack Query**: Server state (API data)
- **Zustand**: Client state (coming soon for UI state)
- **React Context**: Theme, providers

### Routing

Next.js App Router:
- `/` - Dashboard
- `/projects` - Projects list
- `/projects/[id]` - Project details
- `/runs` - Runs list
- `/runs/[id]` - Run details with timeline
- `/artifacts` - Artifacts viewer (placeholder)
- `/review` - Human review (placeholder)
- `/settings` - Settings

## Available Scripts

```bash
# Development
npm run dev          # Start dev server on port 3000

# Production
npm run build        # Build for production
npm start            # Start production server

# Code Quality
npm run lint         # Run ESLint
npm run type-check   # TypeScript type checking
```

## Key Features

### ✅ Implemented

- Application shell with sidebar + top navigation
- Dark/Light/System theme support
- Dashboard with stats cards
- Projects listing with cards
- Runs listing with table
- Run details with workflow timeline
- Responsive layout
- Type-safe API client
- React Query data fetching
- Status badges
- Empty states
- Loading skeletons

### 🔄 Placeholders (Coming Soon)

- Create Project wizard
- Project details page
- Artifacts viewer
- Human review interface
- Search functionality
- Notifications
- User profile
- Code generation
- Test execution
- Reporting

## Troubleshooting

### Backend Connection Issues

If you see API errors:

1. Verify backend is running: `curl http://localhost:8000/health`
2. Check NEXT_PUBLIC_API_URL in `.env.local`
3. Check browser console for CORS errors

### Build Errors

```bash
# Clear Next.js cache
rm -rf .next

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Rebuild
npm run build
```

### TypeScript Errors

```bash
# Run type check
npm run type-check

# Check for missing dependencies
npm install --save-dev @types/node @types/react @types/react-dom
```

## Customization

### Theme Colors

Edit `src/app/globals.css` to customize colors:

```css
:root {
  --primary: 240 5.9% 10%;
  --background: 0 0% 100%;
  /* ... */
}

.dark {
  --primary: 0 0% 98%;
  --background: 240 10% 3.9%;
  /* ... */
}
```

### API Endpoint

Change in `.env.local`:

```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

## Production Deployment

### Vercel (Recommended)

```bash
npm install -g vercel
vercel
```

### Docker

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Manual

```bash
npm run build
npm start
```

## Development Tips

1. **Hot Reload**: Changes auto-reload in dev mode
2. **TypeScript**: Use strict types for API responses
3. **React Query**: Leverage caching and auto-refetch
4. **Tailwind**: Use utility classes for consistent styling
5. **Components**: Keep components small and reusable

## Next Steps

1. Implement Create Project wizard
2. Add project details page
3. Implement search functionality
4. Add real-time updates for runs
5. Build artifacts viewer
6. Implement human review interface
7. Add user authentication
8. Implement notification system

## Support

For issues or questions:
- Check backend logs
- Verify API responses in browser DevTools
- Review React Query DevTools (install extension)
- Check console for errors
