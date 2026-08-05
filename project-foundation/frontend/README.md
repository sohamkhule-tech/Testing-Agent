# AI Testing Platform Frontend

Enterprise-grade frontend for the AI Agentic Web Application Testing Platform.

## Tech Stack

- **Framework**: Next.js 15
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui, Radix UI
- **Icons**: Lucide React
- **State Management**: Zustand
- **Data Fetching**: TanStack Query
- **Tables**: TanStack Table
- **Forms**: React Hook Form + Zod
- **Theme**: next-themes

## Getting Started

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── src/
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # Reusable UI components
│   ├── features/            # Feature-specific modules
│   ├── hooks/               # Custom React hooks
│   ├── lib/                 # Utilities and helpers
│   ├── services/            # API clients
│   ├── store/               # Zustand stores
│   └── types/               # TypeScript types
├── public/                  # Static assets
└── [config files]
```

## Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Features

- ✅ Dark/Light/System theme support
- ✅ Responsive layout
- ✅ Projects management
- ✅ Workflow monitoring
- ✅ Run tracking
- ✅ Centralized API layer
- ✅ Type-safe data fetching
- ✅ Form validation
- ✅ Modular architecture

## Backend

This frontend connects to the Python FastAPI backend running on port 8000.
