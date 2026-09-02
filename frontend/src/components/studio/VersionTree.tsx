import { useStudioStore } from '../../stores/studio'
import { useT } from '../../i18n'
import type { VersionTreeNode } from '../../types/api'
import { versionSourceLabel } from '../../lib/format'

/** 计算每个节点深度（parent_version_id 自引用链） */
function depthOf(nodes: VersionTreeNode[], node: VersionTreeNode): number {
  const map = new Map(nodes.map((n) => [n.id, n]))
  let depth = 0
  let cur: VersionTreeNode | undefined = node
  while (cur?.parent_version_id) {
    cur = map.get(cur.parent_version_id)
    depth++
    if (depth > 20) break
  }
  return depth
}

/** 版本树侧栏（GET /works/{id}/versions，前端构树）+ 最近操作日志 */
export default function VersionTree() {
  const t = useT()
  const versionTree = useStudioStore((s) => s.versionTree)
  const workId = useStudioStore((s) => s.workId)
  const opLog = useStudioStore((s) => s.opLog)
  const resetForNewWork = useStudioStore((s) => s.resetForNewWork)

  const nodes = [...(versionTree?.nodes ?? [])].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  return (
    <div className="border-l px-5 py-5 overflow-y-auto" style={{ borderColor: 'var(--line)' }}>
      <div className="flex items-center justify-between">
        <div className="label">{t('studio.tree.title')}</div>
        {workId && (
          <button
            className="text-[10px] font-bold"
            style={{ color: 'var(--acc)' }}
            onClick={() => resetForNewWork()}
            title={t('studio.tree.newTitle')}
          >
            {t('studio.tree.new')}
          </button>
        )}
      </div>
      <div className="vtree mt-3">
        {nodes.length === 0 ? (
          <div className="text-[11px] py-2 leading-relaxed" style={{ color: 'var(--dim)' }}>
            {t('studio.tree.empty')}
          </div>
        ) : (
          nodes.map((n, i) => (
            <div
              key={n.id}
              className={`vnode pop ${versionTree?.current_version_id === n.id ? 'cur' : ''}`}
              style={{ marginLeft: depthOf(nodes, n) * 14, animationDelay: `${i * 0.05}s` }}
              title={t('studio.tree.node', {
                no: n.version_no,
                source: versionSourceLabel(n.source),
                n: n.candidate_count,
              })}
            >
              <span className="dot"></span>
              {n.version_no} · {versionSourceLabel(n.source)}
            </div>
          ))
        )}
      </div>
      <div className="label mt-6">{t('studio.tree.recentOps')}</div>
      <div className="mt-2 space-y-2 text-[11px]" style={{ color: 'var(--dim)' }}>
        {opLog.map((op, i) => (
          <div key={`${op}-${i}`}>· {op}</div>
        ))}
      </div>
    </div>
  )
}
