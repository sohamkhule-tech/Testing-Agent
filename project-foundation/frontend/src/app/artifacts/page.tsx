'use client';

import { PageHeader } from '@/components/page-header';
import { EmptyState } from '@/components/empty-state';
import { FileText } from 'lucide-react';

export default function ArtifactsPage() {
  return (
    <div className="container py-6">
      <PageHeader
        title="Artifacts"
        description="View and download test artifacts and reports"
      />
      <EmptyState
        icon={FileText}
        title="Artifacts viewer coming soon"
        description="This feature will allow you to browse and download generated artifacts including crawl packages, inventories, test plans, and review metadata."
      />
    </div>
  );
}
