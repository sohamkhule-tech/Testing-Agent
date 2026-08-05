import { WorkflowPhaseStatus } from '@/types/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Circle, Loader2, XCircle, Clock } from 'lucide-react';
import { formatDateTime, formatDuration } from '@/lib/utils';
import { cn } from '@/lib/utils';

interface WorkflowTimelineProps {
  phases: WorkflowPhaseStatus[];
  className?: string;
}

export function WorkflowTimeline({ phases, className }: WorkflowTimelineProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Workflow Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {phases.map((phase, index) => (
            <TimelineItem
              key={phase.phase}
              phase={phase}
              isLast={index === phases.length - 1}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface TimelineItemProps {
  phase: WorkflowPhaseStatus;
  isLast: boolean;
}

function TimelineItem({ phase, isLast }: TimelineItemProps) {
  const statusConfig = getPhaseStatusConfig(phase.status);
  const Icon = statusConfig.icon;
  const phaseLabels: Record<string, string> = {
    trigger: 'Trigger',
    crawler: 'AI Crawler',
    inventory: 'Inventory Aggregation',
    test_design: 'Test Design',
    human_review: 'Human Review',
    code_generation: 'Code Generation',
    execution: 'Test Execution',
    reporting: 'Reporting',
  };

  return (
    <div className="flex gap-4 relative">
      {/* Timeline Line */}
      {!isLast && (
        <div className="absolute left-[15px] top-8 bottom-0 w-[2px] bg-border" />
      )}

      {/* Icon */}
      <div className={cn(
        'relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2',
        statusConfig.borderColor,
        statusConfig.bgColor
      )}>
        <Icon className={cn('h-4 w-4', statusConfig.iconColor)} />
      </div>

      {/* Content */}
      <div className="flex-1 pb-4">
        <div className="flex items-center justify-between mb-1">
          <h4 className="font-semibold">{phaseLabels[phase.phase] || phase.phase}</h4>
          <Badge variant={statusConfig.badgeVariant as any} className="text-xs">
            {statusConfig.label}
          </Badge>
        </div>

        {phase.started_at && (
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>Started: {formatDateTime(phase.started_at)}</span>
            {phase.completed_at && (
              <>
                <span>•</span>
                <span>Completed: {formatDateTime(phase.completed_at)}</span>
              </>
            )}
            {phase.duration_seconds && (
              <>
                <span>•</span>
                <span>Duration: {formatDuration(phase.duration_seconds)}</span>
              </>
            )}
          </div>
        )}

        {phase.error && (
          <div className="mt-2 rounded-md bg-destructive/10 p-2 text-sm text-destructive">
            {phase.error}
          </div>
        )}
      </div>
    </div>
  );
}

function getPhaseStatusConfig(status: string) {
  const configs = {
    pending: {
      icon: Circle,
      label: 'Pending',
      borderColor: 'border-muted',
      bgColor: 'bg-background',
      iconColor: 'text-muted-foreground',
      badgeVariant: 'secondary',
    },
    running: {
      icon: Loader2,
      label: 'Running',
      borderColor: 'border-blue-500',
      bgColor: 'bg-blue-500/10',
      iconColor: 'text-blue-500 animate-spin',
      badgeVariant: 'info',
    },
    completed: {
      icon: CheckCircle2,
      label: 'Completed',
      borderColor: 'border-green-500',
      bgColor: 'bg-green-500/10',
      iconColor: 'text-green-500',
      badgeVariant: 'success',
    },
    failed: {
      icon: XCircle,
      label: 'Failed',
      borderColor: 'border-destructive',
      bgColor: 'bg-destructive/10',
      iconColor: 'text-destructive',
      badgeVariant: 'destructive',
    },
  };

  return configs[status as keyof typeof configs] || configs.pending;
}
