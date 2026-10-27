import { useState, useRef, useMemo, useEffect, type ReactNode, type MouseEvent, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Network, Plus, Minus, Maximize2, X, Search, Crosshair, Download, ChevronDown } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { hierarchy, tree as d3tree } from 'd3-hierarchy';
import * as XLSX from 'xlsx';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';
import DetailRow from '@/factorial/components/cabinet/DetailRow';
import { getCurrentOrganization } from '@/services/api/auth';
import { getMyProfile } from '@/factorial/api/employees';
import { getOrgChart, setManager, assignEmployee, type OrgUnitNode, type PersonNode } from '@/factorial/api/orgUnits';

const NAV = [
  { label: 'Сотрудники', href: '/factorial/employees', end: true },
  { label: 'Команды', href: '/factorial/employees/teams' },
  { label: 'Оргсхема', href: '/factorial/employees/org-chart' },
];

const NODE_W = 190, NODE_H = 96, GAP_X = 26, GAP_Y = 60;
const PALETTE = ['#6366F1', '#EC4899', '#10B981', '#F59E0B', '#0EA5E9', '#8B5CF6', '#EF4444', '#14B8A6', '#F97316', '#3B82F6'];
const initials = (name: string) =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() || '').join('') || '—';
const colorForValue = (key: string): string => {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
};

type GroupKey = 'unit' | 'manager' | 'position' | 'hired';
const GROUPS: { key: GroupKey; label: string }[] = [
  { key: 'unit', label: 'Отдел' },
  { key: 'manager', label: 'Руководитель' },
  { key: 'position', label: 'Должность' },
  { key: 'hired', label: 'Нанят' },
];

type TNode = {
  kind: 'company' | 'unit' | 'emp';
  id: string;
  empId?: number;
  unitId?: number | null;
  name: string;
  position?: string;
  person?: PersonNode;
  deptColor?: string;
  count?: number;
  childCount: number;
  children?: TNode[];
};

const CSS = `
.fx-oc-box { display:flex; flex-direction:column; align-items:center; gap:3px; background:#fff; border:1px solid #E2E8F0; border-radius:14px; padding:10px 10px 9px; box-shadow:0 1px 3px rgba(15,23,42,.08); cursor:pointer; transition:box-shadow .12s, border-color .12s; }
.fx-oc-card:hover .fx-oc-box { border-color:#C7D2FE; box-shadow:0 4px 14px rgba(99,102,241,.16); }
.fx-oc-box--unit { flex-direction:row; gap:9px; align-items:center; padding:11px 12px; border-radius:14px; }
.fx-oc-unitbar { width:6px; align-self:stretch; min-height:30px; border-radius:999px; flex:none; }
.fx-oc-av { width:46px; height:46px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:15px; }
.fx-oc-name { font-weight:600; font-size:13px; color:#0F172A; max-width:168px; text-align:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fx-oc-pos { font-size:11px; color:#64748B; max-width:168px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fx-oc-badge { display:inline-flex; align-items:center; gap:5px; font-size:11px; padding:2px 8px; border-radius:999px; max-width:168px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px; }
.fx-oc-dot { width:7px; height:7px; border-radius:999px; flex:none; }
.fx-oc-toggle { position:absolute; left:50%; bottom:-13px; transform:translateX(-50%); z-index:3; display:inline-flex; align-items:center; gap:2px; background:#fff; border:1px solid #CBD5E1; border-radius:999px; padding:1px 7px; font-size:11px; color:#475569; cursor:pointer; box-shadow:0 1px 2px rgba(15,23,42,.10); }
.fx-oc-toggle:hover { background:#F8FAFC; color:#0F172A; }
.fx-oc-drop .fx-oc-box { outline:2px solid #6366F1; outline-offset:2px; }
`;

export default function EmployeesOrgChartPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ['fx', 'org-chart'], queryFn: getOrgChart });
  const { data: org } = useQuery({ queryKey: ['fx', 'org-current'], queryFn: getCurrentOrganization, retry: false });
  const { data: me } = useQuery({ queryKey: ['fx', 'me'], queryFn: getMyProfile, retry: false });
  const orgName = org?.name || 'Организация';
  const refresh = () => qc.invalidateQueries({ queryKey: ['fx', 'org-chart'] });
  const mManager = useMutation({ mutationFn: (v: { id: number; manager: number | null }) => setManager(v.id, v.manager), onSuccess: refresh, onError: () => {} });
  const mAssign = useMutation({ mutationFn: (v: { id: number; unit: number | null }) => assignEmployee(v.id, v.unit), onSuccess: refresh, onError: () => {} });

  const units: OrgUnitNode[] = data?.units ?? [];
  const people: PersonNode[] = data?.people ?? [];
  const unitName = (id: number | null | undefined) => (id ? units.find((u) => u.id === id)?.name : undefined);
  const unitColor = (id: number | null | undefined) => (id ? units.find((u) => u.id === id)?.color : undefined);
  const nameById = useMemo(() => new Map(people.map((p) => [p.id, p.user_name || '—'])), [people]);

  const [groupKey, setGroupKey] = useState<GroupKey>('unit');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setCollapsed((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const treeData = useMemo<TNode>(() => {
    const buildPerson = (p: PersonNode): TNode => ({
      kind: 'emp', id: 'e' + p.id, empId: p.id, name: p.user_name || '—',
      position: p.position || '', person: p, childCount: 0,
    });
    const company = (children: TNode[]): TNode => {
      const c: TNode = { kind: 'company', id: 'root', name: orgName, childCount: children.length };
      if (children.length && !collapsed.has('root')) c.children = children;
      return c;
    };

    // По руководителю — дерево подчинённости
    if (groupKey === 'manager') {
      const byMgr = new Map<number | null, PersonNode[]>();
      people.forEach((p) => { const m = p.manager_id ?? null; if (!byMgr.has(m)) byMgr.set(m, []); byMgr.get(m)!.push(p); });
      const ids = new Set(people.map((p) => p.id));
      const seen = new Set<number>();
      const build = (p: PersonNode): TNode => {
        seen.add(p.id);
        const kids = (byMgr.get(p.id) || []).filter((c) => !seen.has(c.id));
        const node: TNode = { kind: 'emp', id: 'e' + p.id, empId: p.id, name: p.user_name || '—', position: p.position || '', person: p, childCount: kids.length };
        if (kids.length && !collapsed.has(node.id)) node.children = kids.map(build);
        return node;
      };
      const roots = people.filter((p) => p.manager_id == null || !ids.has(p.manager_id));
      return company(roots.map(build));
    }

    // По отделу — Организация → Департамент (вложенные) → Сотрудники
    if (groupKey === 'unit') {
      const unitsByParent = new Map<number | null, OrgUnitNode[]>();
      units.forEach((u) => { const k = u.parent_id ?? null; if (!unitsByParent.has(k)) unitsByParent.set(k, []); unitsByParent.get(k)!.push(u); });
      const peopleByUnit = new Map<number | null, PersonNode[]>();
      people.forEach((p) => { const k = p.org_unit_id ?? null; if (!peopleByUnit.has(k)) peopleByUnit.set(k, []); peopleByUnit.get(k)!.push(p); });
      // Внутри отдела — дерево по руководителю: lead сверху (нет руководителя в этом отделе), подчинённые под ним
      const forest = (ppl: PersonNode[]): TNode[] => {
        const scope = new Set(ppl.map((p) => p.id));
        const byMgr = new Map<number, PersonNode[]>();
        ppl.forEach((p) => { if (p.manager_id != null && scope.has(p.manager_id)) { if (!byMgr.has(p.manager_id)) byMgr.set(p.manager_id, []); byMgr.get(p.manager_id)!.push(p); } });
        const seen = new Set<number>();
        const buildP = (p: PersonNode): TNode => {
          seen.add(p.id);
          const kids = (byMgr.get(p.id) || []).filter((c) => !seen.has(c.id));
          const node: TNode = { kind: 'emp', id: 'e' + p.id, empId: p.id, name: p.user_name || '—', position: p.position || '', person: p, childCount: kids.length };
          if (kids.length && !collapsed.has(node.id)) node.children = kids.map(buildP);
          return node;
        };
        return ppl.filter((p) => p.manager_id == null || !scope.has(p.manager_id)).map(buildP);
      };
      const buildUnit = (u: OrgUnitNode): TNode => {
        const ppl = peopleByUnit.get(u.id) || [];
        const kids = [...(unitsByParent.get(u.id) || []).map(buildUnit), ...forest(ppl)];
        const node: TNode = { kind: 'unit', id: 'u' + u.id, unitId: u.id, name: u.name, deptColor: u.color || colorForValue(u.name), count: ppl.length, childCount: kids.length };
        if (kids.length && !collapsed.has(node.id)) node.children = kids;
        return node;
      };
      const top = [...(unitsByParent.get(null) || []).map(buildUnit), ...forest(peopleByUnit.get(null) || [])];
      return company(top);
    }

    // По должности / дате найма — Организация → значение → Сотрудники
    const valOf = (p: PersonNode): string =>
      groupKey === 'position' ? (p.position || 'Без должности')
        : (p.hired_at ? String(new Date(p.hired_at).getFullYear()) : 'Не указано');
    const byVal = new Map<string, PersonNode[]>();
    people.forEach((p) => { const v = valOf(p); if (!byVal.has(v)) byVal.set(v, []); byVal.get(v)!.push(p); });
    const groups = [...byVal.entries()].map(([val, ppl]): TNode => {
      const node: TNode = { kind: 'unit', id: 'g:' + val, name: val, deptColor: colorForValue(val), count: ppl.length, childCount: ppl.length };
      if (ppl.length && !collapsed.has(node.id)) node.children = ppl.map(buildPerson);
      return node;
    });
    return company(groups);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [people, units, orgName, groupKey, collapsed]);

  const layout = useMemo(() => {
    const root = d3tree<TNode>().nodeSize([NODE_W + GAP_X, NODE_H + GAP_Y]).separation((a, b) => (a.parent === b.parent ? 1 : 1.25))(hierarchy<TNode>(treeData));
    const nodes = root.descendants();
    const links = root.links();
    let minX = Infinity, maxX = -Infinity, maxY = 0;
    nodes.forEach((n) => { minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y); });
    if (!isFinite(minX)) { minX = 0; maxX = 0; }
    return { nodes, links, minX, width: (maxX - minX) + NODE_W, height: maxY + NODE_H };
  }, [treeData]);

  const leftOf = (n: { x: number }) => n.x - layout.minX;
  const cxOf = (n: { x: number }) => n.x - layout.minX + NODE_W / 2;

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const fitted = useRef(false);

  const onDown = (e: MouseEvent) => {
    if ((e.target as HTMLElement).closest('.fx-oc-card, .fx-oc-toggle, button, input, select')) return;
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    setPanning(true);
  };
  const onMove = (e: MouseEvent) => { if (drag.current) setPan({ x: drag.current.px + (e.clientX - drag.current.x), y: drag.current.py + (e.clientY - drag.current.y) }); };
  const onUp = () => { drag.current = null; setPanning(false); };

  const fit = () => {
    const vp = viewportRef.current; if (!vp) return;
    const z = Math.min((vp.clientWidth - 48) / layout.width, (vp.clientHeight - 48) / layout.height, 1.3);
    const nz = z > 0.25 ? +z.toFixed(2) : 0.25;
    setZoom(nz);
    setPan({ x: (vp.clientWidth - layout.width * nz) / 2, y: 24 });
  };
  useEffect(() => {
    fitted.current = false;
  }, [groupKey]);
  useEffect(() => {
    if (!fitted.current && layout.nodes.length > 1) { fitted.current = true; fit(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout.width, layout.height]);

  const centerOn = (n: { x: number; y: number }) => {
    const vp = viewportRef.current; if (!vp) return;
    setPan({ x: vp.clientWidth / 2 - cxOf(n) * zoom, y: vp.clientHeight / 2 - (n.y + NODE_H / 2) * zoom });
  };

  const [q, setQ] = useState('');
  const query = q.trim().toLowerCase();
  const findMe = () => {
    if (!me) return;
    const n = layout.nodes.find((d) => d.data.empId === (me as { id?: number }).id);
    if (n) { centerOn(n); setQ(n.data.name); }
  };

  const exportXls = () => {
    const rows = people.map((p) => ({
      'Имя': p.user_name || '',
      'Должность': p.position || '',
      'Отдел': unitName(p.org_unit_id) || '',
      'Руководитель': p.manager_id ? (nameById.get(p.manager_id) || '') : '',
      'Нанят': p.hired_at ? new Date(p.hired_at).toLocaleDateString('ru-RU') : '',
    }));
    const ws = XLSX.utils.json_to_sheet(rows.length ? rows : [{ 'Имя': '', 'Должность': '', 'Отдел': '', 'Руководитель': '', 'Нанят': '' }]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Оргсхема');
    XLSX.writeFile(wb, 'orgchart.xlsx');
  };

  const allow = (e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; (e.currentTarget as HTMLElement).classList.add('fx-oc-drop'); };
  const leave = (e: DragEvent) => (e.currentTarget as HTMLElement).classList.remove('fx-oc-drop');
  const onDropNode = (d: TNode, e: DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    (e.currentTarget as HTMLElement).classList.remove('fx-oc-drop');
    const raw = e.dataTransfer.getData('text/plain');
    const id = Number((raw || '').replace('emp:', ''));
    if (!id) return;
    if (d.kind === 'unit' && d.unitId != null) mAssign.mutate({ id, unit: d.unitId });        // в отдел
    else if (d.kind === 'company') mAssign.mutate({ id, unit: null });                          // убрать из отдела
    else if (d.kind === 'emp' && d.empId && id !== d.empId) mManager.mutate({ id, manager: d.empId }); // назначить руководителя
  };

  const [sel, setSel] = useState<TNode | null>(null);

  const card = (n: { data: TNode; x: number; y: number }): ReactNode => {
    const d = n.data;
    const dim = !!query && d.kind === 'emp' && !d.name.toLowerCase().includes(query);
    const hit = !!query && d.kind === 'emp' && d.name.toLowerCase().includes(query);
    const toggleBtn = d.childCount > 0 ? (
      <button type="button" className="fx-oc-toggle" onClick={(e) => { e.stopPropagation(); toggle(d.id); }} title={collapsed.has(d.id) ? 'Развернуть' : 'Свернуть'}>
        <span>{d.childCount}</span>
        <ChevronDown className="w-3 h-3" style={{ transform: collapsed.has(d.id) ? 'rotate(-90deg)' : 'none', transition: 'transform .15s' }} />
      </button>
    ) : null;
    let inner: ReactNode;
    if (d.kind === 'company') {
      inner = (
        <div className="fx-oc-box">
          <div className="fx-oc-av" style={{ background: '#0F172A', color: '#fff' }}>{initials(d.name)}</div>
          <div className="fx-oc-name">{d.name}</div>
          <span className="fx-oc-badge" style={{ background: '#0F172A1A', color: '#0F172A' }}>{people.length} чел.</span>
        </div>
      );
    } else if (d.kind === 'unit') {
      const color = d.deptColor || '#64748B';
      inner = (
        <div className="fx-oc-box fx-oc-box--unit">
          <span className="fx-oc-unitbar" style={{ background: color }} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="fx-oc-name" style={{ textAlign: 'left' }}>{d.name}</div>
            <div className="fx-oc-pos">{d.count || 0} чел.</div>
          </div>
        </div>
      );
    } else {
      const dept = unitName(d.person?.org_unit_id) || 'Без отдела';
      const color = unitColor(d.person?.org_unit_id) || colorForValue(dept);
      inner = (
        <div className="fx-oc-box" style={{ boxShadow: hit ? '0 0 0 2px #6366F1' : undefined, borderColor: hit ? '#6366F1' : undefined }}>
          <div className="fx-oc-av" style={{ background: color + '1A', color }}>{initials(d.name)}</div>
          <div className="fx-oc-name">{d.name}</div>
          {d.position && <div className="fx-oc-pos">{d.position}</div>}
          <span className="fx-oc-badge" style={{ background: color + '1A', color }}><i className="fx-oc-dot" style={{ background: color }} />{dept}</span>
        </div>
      );
    }
    return (
      <div key={d.id} className="fx-oc-card" style={{ position: 'absolute', left: leftOf(n), top: n.y, width: NODE_W, opacity: dim ? 0.3 : 1 }}
        draggable={d.kind === 'emp'}
        onClick={() => setSel(d)}
        onDragStart={d.kind === 'emp' ? (e) => { e.dataTransfer.setData('text/plain', 'emp:' + d.empId); e.dataTransfer.effectAllowed = 'move'; } : undefined}
        onDragOver={allow} onDragLeave={leave} onDrop={(e) => onDropNode(d, e)}>
        {inner}
        {toggleBtn}
      </div>
    );
  };

  const drawerAvatar = (d: TNode) => {
    if (d.kind === 'company') return { bg: '#0F172A', fg: '#fff' };
    if (d.kind === 'unit') { const c = d.deptColor || '#64748B'; return { bg: c + '1A', fg: c }; }
    const dept = unitName(d.person?.org_unit_id) || 'Без отдела';
    const c = unitColor(d.person?.org_unit_id) || colorForValue(dept);
    return { bg: c + '1A', fg: c };
  };

  return (
    <>
      <PageHeader breadcrumb={[{ label: 'Сотрудники', href: '/factorial/employees' }, { label: 'Оргсхема' }]} />
      <div className="px-8 py-6 space-y-4">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-fx-lg bg-indigo-100 flex items-center justify-center"><Network className="w-5 h-5 text-indigo-600" /></div>
          <div>
            <h1 className="text-fx-xl font-semibold leading-tight">Оргсхема</h1>
            <p className="text-fx-xs text-text-muted">Структура по отделам. Перетащите сотрудника на отдел — назначить отдел; на организацию — убрать.</p>
          </div>
        </div>
        <SecondaryNav items={NAV} />

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <select value={groupKey} onChange={(e) => setGroupKey(e.target.value as GroupKey)}
              className="appearance-none pl-3 pr-8 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm font-medium cursor-pointer">
              {GROUPS.map((g) => <option key={g.key} value={g.key}>Группировать: {g.label}</option>)}
            </select>
            <ChevronDown className="w-4 h-4 absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
          </div>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск сотрудника…"
              className="w-full pl-9 pr-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm" />
          </div>
          <button type="button" onClick={findMe} disabled={!me} className="flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm hover:bg-sidebar-hover disabled:opacity-50">
            <Crosshair className="w-4 h-4" />Найти меня
          </button>
          <button type="button" onClick={exportXls} className="flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm hover:bg-sidebar-hover">
            <Download className="w-4 h-4" />Экспорт xls
          </button>
        </div>

        <style>{CSS}</style>
        <div ref={viewportRef}
          className="relative border border-card-border-soft rounded-card overflow-hidden select-none"
          style={{ height: '64vh', background: '#FBFCFE', cursor: panning ? 'grabbing' : 'grab' }}
          onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
          {isLoading ? (
            <div className="absolute inset-0 flex items-center justify-center text-fx-sm text-text-muted">Загрузка…</div>
          ) : people.length === 0 && units.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-fx-sm text-text-muted">Пока нет ни отделов, ни сотрудников.</div>
          ) : (
            <div style={{ position: 'absolute', top: 0, left: 0, transformOrigin: '0 0', transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transition: panning ? 'none' : 'transform .12s ease' }}>
              <svg width={layout.width} height={layout.height} style={{ position: 'absolute', top: 0, left: 0, overflow: 'visible' }}>
                {layout.links.map((l, i) => {
                  const sx = cxOf(l.source), sy = l.source.y + NODE_H, tx = cxOf(l.target), ty = l.target.y, my = (sy + ty) / 2;
                  return <path key={i} d={`M${sx},${sy} V${my} H${tx} V${ty}`} fill="none" stroke="#CBD5E1" strokeWidth={1.5} />;
                })}
              </svg>
              {layout.nodes.map((n) => card(n))}
            </div>
          )}

          <div className="absolute left-3 bottom-3 flex items-center gap-2 z-10">
            <div className="flex items-center bg-white border border-card-border-soft rounded-fx-lg shadow-card overflow-hidden text-fx-sm">
              <button type="button" className="px-2 py-1.5 hover:bg-sidebar-hover" title="Уменьшить" onClick={() => setZoom((z) => Math.max(0.25, +(z - 0.1).toFixed(2)))}><Minus className="w-4 h-4" /></button>
              <button type="button" className="px-3 py-1.5 hover:bg-sidebar-hover border-x border-card-border-soft" onClick={fit}>Подогнать масштаб</button>
              <button type="button" className="px-2 py-1.5 hover:bg-sidebar-hover" title="Увеличить" onClick={() => setZoom((z) => Math.min(1.6, +(z + 0.1).toFixed(2)))}><Plus className="w-4 h-4" /></button>
            </div>
            <button type="button" className="flex items-center gap-1.5 bg-white border border-card-border-soft rounded-fx-lg shadow-card px-3 py-1.5 text-fx-sm hover:bg-sidebar-hover" onClick={() => setCollapsed(new Set())}>
              <Maximize2 className="w-4 h-4" />Развернуть все
            </button>
          </div>
        </div>
      </div>

      {sel && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setSel(null)} />
          <div className="fixed inset-y-0 right-0 w-80 bg-white shadow-2xl border-l border-card-border-soft z-50 flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-card-border-soft">
              <span className="font-semibold text-fx-sm">{sel.kind === 'emp' ? 'Сотрудник' : sel.kind === 'unit' ? 'Отдел' : 'Организация'}</span>
              <button type="button" onClick={() => setSel(null)} className="p-1 rounded hover:bg-sidebar-hover"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-5 space-y-5 overflow-y-auto flex-1">
              <div className="flex flex-col items-center gap-2">
                {(() => { const av = drawerAvatar(sel); return <div className="w-20 h-20 rounded-3xl flex items-center justify-center text-xl font-semibold" style={{ background: av.bg, color: av.fg }}>{initials(sel.name)}</div>; })()}
                <div className="font-semibold text-fx-base text-center">{sel.name}</div>
              </div>
              <div>
                <h3 className="text-fx-sm font-semibold mb-1">Информация</h3>
                {sel.kind === 'emp' ? <>
                  <DetailRow label="Должность" value={sel.position || '—'} />
                  <DetailRow label="Отдел" value={unitName(sel.person?.org_unit_id) || '—'} />
                  <DetailRow label="Руководитель" value={sel.person?.manager_id ? (nameById.get(sel.person.manager_id) || '—') : '—'} />
                  <DetailRow label="Нанят" value={sel.person?.hired_at ? new Date(sel.person.hired_at).toLocaleDateString('ru-RU') : '—'} />
                  <DetailRow label="Юр.лицо" value={orgName} />
                </> : sel.kind === 'unit' ? <>
                  <DetailRow label="Отдел" value={sel.name} />
                  <DetailRow label="Сотрудников" value={String(sel.count || 0)} />
                </> : <>
                  <DetailRow label="Сотрудников" value={String(people.length)} />
                  <DetailRow label="Отделов" value={String(units.length)} />
                </>}
              </div>
            </div>
            {sel.kind === 'emp' && (
              <div className="p-4 border-t border-card-border-soft">
                <button type="button" onClick={() => sel.empId && navigate('/factorial/employees/' + sel.empId)} className="w-full px-3 py-2 rounded-fx-lg text-fx-sm font-medium bg-primary text-white hover:bg-primary-hover">Перейти в профиль</button>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
