'use client';

import Link from 'next/link';
import { Circle, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export function WorkflowStageCard({
  icon: Icon, label, status, runStatus, detail, actions, backendPending,
}: {
  icon: any; label: string; status: 'past' | 'current' | 'pending' | 'failed';
  runStatus?: string; detail: Record<string, string>; actions: { label: string; href: string }[];
  backendPending?: boolean;
}) {
  const isDisabled = status === 'pending';

  const statusColor = status === 'current' && runStatus === 'in_progress' ? 'text-blue-500 border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950' :
    status === 'failed' ? 'text-red-500 border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950' :
    status === 'past' ? 'text-emerald-500 border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950' :
    'text-muted-foreground/40 border-border bg-muted/30';

  const statusIcon = status === 'current' && runStatus === 'in_progress' ? <Loader2 className="h-4 w-4 animate-spin" /> :
    status === 'failed' ? <AlertCircle className="h-4 w-4" /> :
    status === 'past' ? <CheckCircle2 className="h-4 w-4" /> :
    <Circle className="h-4 w-4" />;

  return (
    <Card className={cn("transition-colors", status === 'current' && "ring-1 ring-blue-400 dark:ring-blue-600")}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", statusColor)}>
              {statusIcon}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm font-semibold">{label}</CardTitle>
                {backendPending && <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-muted-foreground">API pending</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                {status === 'past' ? 'Completed' :
                 status === 'current' && runStatus === 'in_progress' ? 'Running...' :
                 status === 'failed' ? 'Failed — review errors' :
                 status === 'current' ? 'Queued' : 'Awaiting previous stage'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {actions.map((a) => (
              <Button key={a.label} variant={isDisabled ? 'outline' : 'secondary'} size="sm" className="h-7 text-xs" disabled={isDisabled} asChild={!isDisabled}>
                {isDisabled ? <span>{a.label}</span> : <Link href={a.href}>{a.label}</Link>}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Object.entries(detail).map(([key, val]) => (
            <div key={key} className="space-y-0.5">
              <p className="text-[11px] text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</p>
              <p className="text-sm font-medium">{val}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
