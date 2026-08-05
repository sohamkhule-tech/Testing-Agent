'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { PageHeader } from '@/components/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { EmptyState } from '@/components/empty-state';
import { StatusBadge } from '@/components/status-badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Plus, FolderKanban, ExternalLink, MoreVertical,
  Globe, Trash2, Edit, X,
} from 'lucide-react';
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
} from '@/hooks/use-api';
import { formatDateTime } from '@/lib/utils';
import type { CreateProjectRequest } from '@/types/api';
import { cn } from '@/lib/utils';

// ── Page ──

export default function ProjectsPage() {
  const { data: projects, isLoading } = useProjects();
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Projects"
        description="Manage your testing projects"
        actions={
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Project
          </Button>
        }
      />

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardHeader><Skeleton className="h-6 w-3/4" /><Skeleton className="h-4 w-full mt-2" /></CardHeader>
              <CardContent><Skeleton className="h-20 w-full" /></CardContent>
            </Card>
          ))}
        </div>
      ) : !projects || projects.length === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No projects yet"
          description="Create your first project to start testing your web applications"
          action={{ label: 'Create Project', onClick: () => setShowCreate(true) }}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <div key={project.id} className="group relative">
              <Link href={`/projects/${project.id}`}>
                <Card className="h-full hover:border-primary transition-colors cursor-pointer">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <CardTitle className="flex items-center gap-2 truncate">{project.name}</CardTitle>
                        <CardDescription className="mt-2 line-clamp-2">
                          {project.description || 'No description'}
                        </CardDescription>
                      </div>
                      <Button variant="ghost" size="icon" className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => { e.preventDefault(); setDeletingId(project.id); }}>
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center gap-2 text-sm">
                      <Globe className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      <span className="text-muted-foreground truncate">{project.application_url}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Total Runs</span>
                      <span className="font-medium">{project.total_runs}</span>
                    </div>
                    {project.last_run_status && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Last Run</span>
                        <StatusBadge status={project.last_run_status} size="sm" />
                      </div>
                    )}
                    {project.pending_reviews > 0 && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Pending Reviews</span>
                        <span className="font-medium text-amber-500">{project.pending_reviews}</span>
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground pt-2 border-t">
                      Created {formatDateTime(project.created_at)}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && <ProjectFormModal onClose={() => setShowCreate(false)} />}

      {/* Edit Modal */}
      {editingId && <ProjectFormModal projectId={editingId} onClose={() => setEditingId(null)} />}

      {/* Delete Modal */}
      {deletingId && <DeleteModal projectId={deletingId} onClose={() => setDeletingId(null)} />}
    </div>
  );
}

// ── Create / Edit Modal ──

function ProjectFormModal({ projectId, onClose }: { projectId?: string; onClose: () => void }) {
  const router = useRouter();
  const createProject = useCreateProject();
  const { data: existing } = useProjects();
  const editData = projectId ? existing?.find((p) => p.id === projectId) : null;

  const [form, setForm] = useState<CreateProjectRequest>({
    name: editData?.name ?? '',
    description: editData?.description ?? '',
    application_url: editData?.application_url ?? '',
    starting_urls: editData?.application_url ? [editData.application_url] : [],
    auth_type: editData?.auth_type,
    max_pages: 50,
    max_depth: 3,
  });
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) { setError('Name is required'); return; }
    if (!form.application_url.trim()) { setError('Application URL is required'); return; }
    try {
      const result = await createProject.mutateAsync(form);
      onClose();
      router.push(`/projects/${result.id}`);
    } catch {
      setError('Failed to create project. Please try again.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>{projectId ? 'Edit Project' : 'New Project'}</CardTitle>
            <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Project Name *</Label>
              <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="My Web App" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="desc">Description</Label>
              <Input id="desc" value={form.description ?? ''} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional description" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="url">Application URL *</Label>
              <Input id="url" value={form.application_url} onChange={(e) => setForm({ ...form, application_url: e.target.value })} placeholder="https://example.com" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="pages">Max Pages</Label>
                <Input id="pages" type="number" value={form.max_pages} onChange={(e) => setForm({ ...form, max_pages: Number(e.target.value) })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="depth">Max Depth</Label>
                <Input id="depth" type="number" value={form.max_depth} onChange={(e) => setForm({ ...form, max_depth: Number(e.target.value) })} />
              </div>
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={createProject.isPending}>
                {createProject.isPending ? 'Creating...' : projectId ? 'Save Changes' : 'Create Project'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Delete Modal ──

function DeleteModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const deleteProject = useDeleteProject();
  const router = useRouter();

  const handleDelete = async () => {
    try {
      await deleteProject.mutateAsync(projectId);
      onClose();
    } catch {
      // handled by react-query
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-lg">Delete Project</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Are you sure? This action cannot be undone.
          </p>
        </CardHeader>
        <CardContent className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={handleDelete} disabled={deleteProject.isPending}>
            {deleteProject.isPending ? 'Deleting...' : 'Delete'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
