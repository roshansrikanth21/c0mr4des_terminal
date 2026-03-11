import React, { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

interface MemoryStatusResponse {
  status: string;
  active_memories?: number;
  expired_memories?: number;
  avg_trust_score?: number;
  avg_drift_score?: number;
  trust_tier_counts?: Record<string, number>;
  validation_state_counts?: Record<string, number>;
  memory_type_counts?: Record<string, number>;
  last_maintenance_at?: string | null;
}

interface MemoryContextResponse {
  status: string;
  retrieved?: Array<{
    memory_id?: string;
    content: string;
    source: string;
    similarity: number;
    directional_hint?: number;
    metadata?: {
      memory_type?: string;
      trust_tier?: string;
      trust_score?: number;
      drift_score?: number;
      validation_state?: string;
      confidence?: number;
      freshness_score?: number;
      ticker?: string | null;
      interval?: string | null;
      setup_family?: string | null;
    };
  }>;
  influence?: {
    memory_count: number;
    alignment_bias: number;
    risk_bias: number;
    average_trust: number;
    average_drift: number;
    notes?: string[];
  };
}

interface MemoryResearchResponse {
  status: string;
  total_memories?: number;
  trust_tiers?: Record<string, number>;
  validation_states?: Record<string, number>;
  type_summary?: Array<{
    memory_type: string;
    count: number;
    avg_trust_score: number;
    avg_drift_score: number;
  }>;
  drifted_memories?: Array<{
    memory_id: string;
    content: string;
    source: string;
    memory_type: string;
    trust_tier: string;
    trust_score: number;
    drift_score: number;
    validation_state: string;
  }>;
  last_maintenance_at?: string | null;
}

export function MemoryLab() {
  const [status, setStatus] = useState<MemoryStatusResponse | null>(null);
  const [context, setContext] = useState<MemoryContextResponse | null>(null);
  const [research, setResearch] = useState<MemoryResearchResponse | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    ticker: '^NSEI',
    interval: '15m',
    query: '',
    regime: '',
    setup_family: '',
    session_bucket: '',
  });
  const [writeForm, setWriteForm] = useState({
    content: '',
    source: 'api_manual_write',
    memory_type: 'strategy',
  });
  const [validationForm, setValidationForm] = useState({
    memory_id: '',
    outcome: 'success',
  });

  const loadStatus = async () => {
    const res = await fetch('/api/memory/status');
    setStatus(await res.json());
  };

  const loadContext = async () => {
    const query = new URLSearchParams({
      ticker: filters.ticker,
      interval: filters.interval,
      query: filters.query,
      regime: filters.regime,
      setup_family: filters.setup_family,
      session_bucket: filters.session_bucket,
      limit: '12',
    });
    const res = await fetch(`/api/memory/context?${query.toString()}`);
    setContext(await res.json());
  };

  const loadResearch = async () => {
    const query = new URLSearchParams({
      ticker: filters.ticker,
      interval: filters.interval,
    });
    const res = await fetch(`/api/memory/research?${query.toString()}`);
    setResearch(await res.json());
  };

  const refreshAll = async () => {
    setIsBusy(true);
    try {
      await Promise.all([loadStatus(), loadContext(), loadResearch()]);
    } finally {
      setIsBusy(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  const runMaintenance = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/memory/maintenance', { method: 'POST' });
      const data = await res.json();
      setMessage(`Maintenance complete: ${data?.remaining ?? 0} kept, ${data?.pruned ?? 0} pruned.`);
      await refreshAll();
    } finally {
      setIsBusy(false);
    }
  };

  const writeMemory = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/memory/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: writeForm.content,
          source: writeForm.source,
          metadata: {
            memory_type: writeForm.memory_type,
            ticker: filters.ticker,
            interval: filters.interval,
            regime: filters.regime || undefined,
            setup_family: filters.setup_family || undefined,
          },
        }),
      });
      const data = await res.json();
      setMessage(data?.status === 'success' ? 'Memory written.' : (data?.message || 'Memory write failed.'));
      if (data?.status === 'success') {
        setWriteForm((prev) => ({ ...prev, content: '' }));
      }
      await refreshAll();
    } finally {
      setIsBusy(false);
    }
  };

  const validateMemory = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/memory/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          memory_id: validationForm.memory_id,
          outcome: validationForm.outcome,
          details: {
            ticker: filters.ticker,
            interval: filters.interval,
            operator_note: 'memory_lab_manual_validation',
          },
        }),
      });
      const data = await res.json();
      setMessage(data?.status === 'success' ? 'Memory validation recorded.' : (data?.message || 'Validation failed.'));
      await refreshAll();
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter uppercase">Memory Lab</h1>
          <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">
            Trust tiers, drift review, maintenance, scoped retrieval, and manual validation.
          </p>
        </div>
        <Button onClick={refreshAll} disabled={isBusy} className="font-mono uppercase tracking-wider">
          Refresh Memory
        </Button>
      </div>

      {message && (
        <div className="rounded-lg border border-border/60 bg-secondary/30 px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
          {message}
        </div>
      )}

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <CardTitle className="text-lg font-mono uppercase tracking-widest">Scope Controls</CardTitle>
        </CardHeader>
        <CardContent className="pt-6 grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <Input value={filters.ticker} onChange={(e) => setFilters((prev) => ({ ...prev, ticker: e.target.value }))} placeholder="Ticker" />
          <Input value={filters.interval} onChange={(e) => setFilters((prev) => ({ ...prev, interval: e.target.value }))} placeholder="Interval" />
          <Input value={filters.query} onChange={(e) => setFilters((prev) => ({ ...prev, query: e.target.value }))} placeholder="Query" />
          <Input value={filters.regime} onChange={(e) => setFilters((prev) => ({ ...prev, regime: e.target.value }))} placeholder="Regime" />
          <Input value={filters.setup_family} onChange={(e) => setFilters((prev) => ({ ...prev, setup_family: e.target.value }))} placeholder="Setup" />
          <Select value={filters.session_bucket || 'any'} onValueChange={(value) => setFilters((prev) => ({ ...prev, session_bucket: value === 'any' ? '' : value }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any Session</SelectItem>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="midday">Midday</SelectItem>
              <SelectItem value="close">Close</SelectItem>
              <SelectItem value="offhours">Offhours</SelectItem>
            </SelectContent>
          </Select>
          <div className="md:col-span-3 xl:col-span-6 flex flex-wrap gap-3">
            <Button onClick={loadContext} disabled={isBusy} className="font-mono uppercase tracking-wider">Load Context</Button>
            <Button onClick={loadResearch} disabled={isBusy} variant="secondary" className="font-mono uppercase tracking-wider">Load Research</Button>
            <Button onClick={runMaintenance} disabled={isBusy} variant="secondary" className="font-mono uppercase tracking-wider">Run Maintenance</Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
        <Card className="border border-primary/20 bg-secondary/10"><CardContent className="pt-6"><div className="text-[10px] font-mono uppercase text-muted-foreground">Active</div><div className="font-mono text-2xl">{status?.active_memories ?? 0}</div></CardContent></Card>
        <Card className="border border-primary/20 bg-secondary/10"><CardContent className="pt-6"><div className="text-[10px] font-mono uppercase text-muted-foreground">Expired</div><div className="font-mono text-2xl">{status?.expired_memories ?? 0}</div></CardContent></Card>
        <Card className="border border-primary/20 bg-secondary/10"><CardContent className="pt-6"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Trust</div><div className="font-mono text-2xl">{(((status?.avg_trust_score ?? 0) * 100)).toFixed(0)}%</div></CardContent></Card>
        <Card className="border border-primary/20 bg-secondary/10"><CardContent className="pt-6"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Drift</div><div className="font-mono text-2xl">{(((status?.avg_drift_score ?? 0) * 100)).toFixed(0)}%</div></CardContent></Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden xl:col-span-2">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Scoped Context</CardTitle>
            <CardDescription>
              Retrieved memories with trust, drift, and directional context.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Trust</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Drift</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">State</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Content</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(context?.retrieved || []).length ? (
                  <TableRow><TableCell colSpan={6} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No memory context loaded</TableCell></TableRow>
                ) : (
                  context!.retrieved!.map((row) => (
                    <TableRow key={row.memory_id || `${row.source}-${row.content}`}>
                      <TableCell className="font-mono text-xs uppercase">{row.metadata?.memory_type || 'n/a'}</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.metadata?.trust_tier || 'n/a'} {(((row.metadata?.trust_score ?? 0) * 100)).toFixed(0)}%</TableCell>
                      <TableCell className="font-mono text-xs">{(((row.metadata?.drift_score ?? 0) * 100)).toFixed(0)}%</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.metadata?.validation_state || 'n/a'}</TableCell>
                      <TableCell className="font-mono text-xs">{row.similarity.toFixed(2)}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{row.content}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Influence</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-3">
            <div className="text-xs font-mono uppercase">Align Bias: {(context?.influence?.alignment_bias ?? 0).toFixed(2)}</div>
            <div className="text-xs font-mono uppercase">Risk Bias: {(context?.influence?.risk_bias ?? 0).toFixed(2)}</div>
            <div className="text-xs font-mono uppercase">Avg Trust: {(((context?.influence?.average_trust ?? 0) * 100)).toFixed(0)}%</div>
            <div className="text-xs font-mono uppercase">Avg Drift: {(((context?.influence?.average_drift ?? 0) * 100)).toFixed(0)}%</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(status?.trust_tier_counts || {}).map(([key, value]) => (
                <Badge key={key} variant="secondary" className="font-mono uppercase">{key}:{value}</Badge>
              ))}
            </div>
            <div className="space-y-2">
              {(context?.influence?.notes || []).map((note) => (
                <div key={note} className="text-xs font-mono text-muted-foreground">{note}</div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Type Summary</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Count</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Trust</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Drift</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(research?.type_summary || []).length ? (
                  <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No research summary</TableCell></TableRow>
                ) : (
                  research!.type_summary!.map((row) => (
                    <TableRow key={row.memory_type}>
                      <TableCell className="font-mono text-xs uppercase">{row.memory_type}</TableCell>
                      <TableCell className="font-mono text-xs">{row.count}</TableCell>
                      <TableCell className="font-mono text-xs">{(row.avg_trust_score * 100).toFixed(0)}%</TableCell>
                      <TableCell className="font-mono text-xs">{(row.avg_drift_score * 100).toFixed(0)}%</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Drifted Memories</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Drift</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Trust</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Content</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(research?.drifted_memories || []).length ? (
                  <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No drifted memories</TableCell></TableRow>
                ) : (
                  research!.drifted_memories!.map((row) => (
                    <TableRow key={row.memory_id}>
                      <TableCell className="font-mono text-xs uppercase">{row.memory_type}</TableCell>
                      <TableCell className="font-mono text-xs">{(row.drift_score * 100).toFixed(0)}%</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.trust_tier}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{row.content}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Manual Write</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Content</Label>
              <Input value={writeForm.content} onChange={(e) => setWriteForm((prev) => ({ ...prev, content: e.target.value }))} />
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Source</Label>
                <Input value={writeForm.source} onChange={(e) => setWriteForm((prev) => ({ ...prev, source: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Type</Label>
                <Select value={writeForm.memory_type} onValueChange={(value) => setWriteForm((prev) => ({ ...prev, memory_type: value }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="strategy">Strategy</SelectItem>
                    <SelectItem value="market">Market</SelectItem>
                    <SelectItem value="news">News</SelectItem>
                    <SelectItem value="execution">Execution</SelectItem>
                    <SelectItem value="operator">Operator</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button onClick={writeMemory} disabled={isBusy || !writeForm.content.trim()} className="font-mono uppercase tracking-wider">Write Memory</Button>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Manual Validation</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Memory ID</Label>
              <Input value={validationForm.memory_id} onChange={(e) => setValidationForm((prev) => ({ ...prev, memory_id: e.target.value }))} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Outcome</Label>
              <Select value={validationForm.outcome} onValueChange={(value) => setValidationForm((prev) => ({ ...prev, outcome: value }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="failure">Failure</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={validateMemory} disabled={isBusy || !validationForm.memory_id.trim()} className="font-mono uppercase tracking-wider">Record Validation</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
