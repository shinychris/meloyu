import { useStudioStore } from '../../stores/studio'
import { useT } from '../../i18n'
import { depthOf } from '../../lib/tree'
import { versionSourceLabel } from '../../lib/format'

/** 版本树侧栏（GET /works/{id}/versions，前端构树）+ 最近操作日志 */
export default function VersionTree() {
  const t = useT()
  const versionTree = useStudioStore((s) => s.versionTree)
  const workId = useStudioStore((s) => s.workId)
  const opLog = useStudioStore((s) => s.opLog)
  const opLogBaseLogged = useStudioStore((s) => s.opLogBaseLogged)
  const resetForNewWork = useStudioStore((s) => s.resetForNewWork)

  // ：初始「模板已载入」行按当前 locale 现取（store 不在模块加载时冻结文案）
  const logLines = opLogBaseLogged ? opLog : [t('studio.log.templateLoaded'), ...opLog]

  const nodes = [...(versionTree?.nodes ?? [])].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  return (
    <div className="border-l border-line px-5 py-5 overflow-y-auto">
      <div className="flex items-center justify-between">
        <div className="label">{t('studio.tree.title')}</div>
        {workId && (
          <button
            className="text-2xs font-bold text-acc"
            onClick={() => resetForNewWork()}
            title={t('studio.tree.newTitle')}
          >
            {t('studio.tree.new')}
          </button>
        )}
      </div>
      <div className="vtree mt-3">
        {nodes.length === 0 ? (
          <div className="text-xs py-2 leading-relaxed text-dim">
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
      <div className="mt-2 space-y-2 text-xs text-dim">
        {logLines.map((op, i) => (
          <div key={`${op}-${i}`}>· {op}</div>
        ))}
      </div>
    </div>
  )
}
