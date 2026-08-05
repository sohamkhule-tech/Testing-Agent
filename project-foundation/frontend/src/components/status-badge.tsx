import { Badge } from '@/components/ui/badge';
import { RunStatus, ReviewStatus, WorkflowPhase } from '@/types/api';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Loader2, 
  Ban,
  AlertCircle,
} from 'lucide-react';

interface StatusBadgeProps {
  status: RunStatus | ReviewStatus | string;
  size?: 'sm' | 'default';
}

export function StatusBadge({ status, size = 'default' }: StatusBadgeProps) {
  const config = getStatusConfig(status);
  const Icon = config.icon;

  return (
    <Badge 
      variant={config.variant as any} 
      className={size === 'sm' ? 'text-[10px] px-1.5 py-0' : ''}
    >
      <Icon className={size === 'sm' ? 'h-2.5 w-2.5 mr-1' : 'h-3 w-3 mr-1'} />
      {config.label}
    </Badge>
  );
}

function getStatusConfig(status: string) {
  const statusMap: Record<string, { label: string; variant: string; icon: any }> = {
    // Run statuses
    pending: { label: 'Pending', variant: 'secondary', icon: Clock },
    in_progress: { label: 'In Progress', variant: 'info', icon: Loader2 },
    completed: { label: 'Completed', variant: 'success', icon: CheckCircle2 },
    failed: { label: 'Failed', variant: 'destructive', icon: XCircle },
    cancelled: { label: 'Cancelled', variant: 'outline', icon: Ban },
    
    // Review statuses
    draft: { label: 'Draft', variant: 'secondary', icon: Clock },
    under_review: { label: 'Under Review', variant: 'warning', icon: AlertCircle },
    approved: { label: 'Approved', variant: 'success', icon: CheckCircle2 },
    partially_approved: { label: 'Partially Approved', variant: 'warning', icon: CheckCircle2 },
    changes_requested: { label: 'Changes Requested', variant: 'warning', icon: AlertCircle },
    rejected: { label: 'Rejected', variant: 'destructive', icon: XCircle },
    archived: { label: 'Archived', variant: 'outline', icon: Ban },
  };

  return statusMap[status] || { label: status, variant: 'default', icon: Clock };
}

interface PhaseStatusBadgeProps {
  phase: WorkflowPhase;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export function PhaseStatusBadge({ phase, status }: PhaseStatusBadgeProps) {
  const config = getPhaseStatusConfig(status);
  const Icon = config.icon;
  
  const phaseLabels: Record<WorkflowPhase, string> = {
    trigger: 'Trigger',
    crawler: 'Crawler',
    inventory: 'Inventory',
    test_design: 'Test Design',
    human_review: 'Human Review',
    code_generation: 'Code Generation',
    execution: 'Execution',
    reporting: 'Reporting',
  };

  return (
    <Badge variant={config.variant as any} className="gap-1.5">
      <Icon className="h-3 w-3" />
      {phaseLabels[phase]}: {config.label}
    </Badge>
  );
}

function getPhaseStatusConfig(status: string) {
  const statusMap: Record<string, { label: string; variant: string; icon: any }> = {
    pending: { label: 'Pending', variant: 'secondary', icon: Clock },
    running: { label: 'Running', variant: 'info', icon: Loader2 },
    completed: { label: 'Completed', variant: 'success', icon: CheckCircle2 },
    failed: { label: 'Failed', variant: 'destructive', icon: XCircle },
  };

  return statusMap[status] || { label: status, variant: 'default', icon: Clock };
}
