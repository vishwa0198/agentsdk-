import { useState, useCallback, useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  Panel,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { savePipeline, listPipelines, getPipeline, deletePipeline, runPipelineAdhoc } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DEFAULT_MODELS = [
  'llama-3.1-8b-instant',
  'llama-3.3-70b-versatile',
  'qwen/qwen3-32b',
  'gemma2-9b-it',
  'mixtral-8x7b-32768',
]

// ---------------------------------------------------------------------------
// Custom node component
// ---------------------------------------------------------------------------
function AgentNodeComponent({ id, data, selected }) {
  const borderColor = data.isEntry
    ? '#22c55e'
    : data.isExit
    ? '#6366f1'
    : selected
    ? '#3b82f6'
    : 'var(--border, #e5e7eb)'

  const badge = data.isEntry ? (
    <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 10, background: '#22c55e', color: '#fff', fontWeight: 700 }}>ENTRY</span>
  ) : data.isExit ? (
    <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 10, background: '#6366f1', color: '#fff', fontWeight: 700 }}>EXIT</span>
  ) : null

  // Show run result overlay when available
  const resultStyle = data.runResult
    ? { borderLeft: `3px solid ${data.runResult.success ? '#22c55e' : '#ef4444'}` }
    : {}

  return (
    <div style={{
      background: '#fff',
      border: `2px solid ${borderColor}`,
      borderRadius: 10,
      padding: '10px 14px',
      minWidth: 180,
      maxWidth: 240,
      boxShadow: selected ? '0 0 0 3px rgba(59,130,246,0.2)' : '0 2px 8px rgba(0,0,0,0.08)',
      fontSize: 12,
      position: 'relative',
      ...resultStyle,
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#94a3b8', width: 10, height: 10 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: 16 }}>🤖</span>
        <strong style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {data.name || 'Agent'}
        </strong>
        {badge}
      </div>

      <div style={{ color: '#64748b', fontSize: 11, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {data.system_prompt || '—'}
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 8, background: '#f1f5f9', color: '#475569', fontFamily: 'monospace' }}>
          {(data.model || 'llama-3.1-8b-instant').split('/').pop()}
        </span>
        <span style={{ fontSize: 10, color: '#94a3b8' }}>×{data.max_iterations ?? 5}</span>
      </div>

      {/* Run result */}
      {data.runResult && (
        <div style={{
          marginTop: 8, padding: '4px 8px', borderRadius: 6,
          background: data.runResult.success ? '#f0fdf4' : '#fef2f2',
          color: data.runResult.success ? '#166534' : '#dc2626',
          fontSize: 10,
          maxHeight: 60, overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {data.runResult.success
            ? (data.runResult.output || '').slice(0, 120)
            : data.runResult.error}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: '#94a3b8', width: 10, height: 10 }} />
    </div>
  )
}

const NODE_TYPES = { agentNode: AgentNodeComponent }

// ---------------------------------------------------------------------------
// Node config panel (right sidebar)
// ---------------------------------------------------------------------------
function NodeConfigPanel({ node, onChange, onSetEntry, onSetExit, onDelete }) {
  const d = node.data
  const inp = (key, val) => onChange(node.id, { ...d, [key]: val })

  const labelStyle = { fontSize: 11, color: 'var(--text-2, #64748b)', marginBottom: 3, display: 'block' }
  const inputStyle = {
    width: '100%', padding: '6px 8px', borderRadius: 6, fontSize: 12,
    border: '1px solid var(--border, #e5e7eb)', background: 'var(--bg-2, #f9fafb)',
    color: 'var(--text-1)', boxSizing: 'border-box',
  }

  return (
    <div style={{
      width: 260, background: 'var(--bg-1, #fff)', borderLeft: '1px solid var(--border)',
      padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>Node Config</div>

      <label>
        <span style={labelStyle}>Name</span>
        <input style={inputStyle} value={d.name || ''} onChange={e => inp('name', e.target.value)} />
      </label>

      <label>
        <span style={labelStyle}>System Prompt</span>
        <textarea
          style={{ ...inputStyle, minHeight: 80, resize: 'vertical' }}
          value={d.system_prompt || ''}
          onChange={e => inp('system_prompt', e.target.value)}
        />
      </label>

      <label>
        <span style={labelStyle}>Model</span>
        <select style={inputStyle} value={d.model || DEFAULT_MODELS[0]} onChange={e => inp('model', e.target.value)}>
          {DEFAULT_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </label>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <label>
          <span style={labelStyle}>Max iterations</span>
          <input style={inputStyle} type="number" min={1} max={20} value={d.max_iterations ?? 5}
            onChange={e => inp('max_iterations', parseInt(e.target.value, 10))} />
        </label>
        <div />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <label>
          <span style={labelStyle}>Input key</span>
          <input style={inputStyle} value={d.input_key || 'input'} onChange={e => inp('input_key', e.target.value)} />
        </label>
        <label>
          <span style={labelStyle}>Output key</span>
          <input style={inputStyle} value={d.output_key || 'output'} onChange={e => inp('output_key', e.target.value)} />
        </label>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingTop: 4 }}>
        <button onClick={() => onSetEntry(node.id)} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
          background: d.isEntry ? '#22c55e' : 'transparent',
          border: '1px solid #22c55e', color: d.isEntry ? '#fff' : '#22c55e',
        }}>
          {d.isEntry ? '✓ Entry' : 'Set Entry'}
        </button>
        <button onClick={() => onSetExit(node.id)} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
          background: d.isExit ? '#6366f1' : 'transparent',
          border: '1px solid #6366f1', color: d.isExit ? '#fff' : '#6366f1',
        }}>
          {d.isExit ? '✓ Exit' : 'Set Exit'}
        </button>
        <button onClick={() => onDelete(node.id)} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
          background: 'transparent', border: '1px solid #ef4444', color: '#ef4444',
        }}>
          Delete
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run panel (bottom drawer)
// ---------------------------------------------------------------------------
function RunPanel({ nodes, edges, onClose, onResultsReady }) {
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const buildConfig = () => {
    const entryNode = nodes.find(n => n.data.isEntry)
    const exitNode = nodes.find(n => n.data.isExit)
    return {
      id: 'adhoc',
      name: 'Ad-hoc run',
      nodes: nodes.map(n => ({
        id: n.id,
        name: n.data.name || 'Agent',
        system_prompt: n.data.system_prompt || 'You are a helpful assistant.',
        model: n.data.model || 'llama-3.1-8b-instant',
        max_iterations: n.data.max_iterations ?? 5,
        input_key: n.data.input_key || 'input',
        output_key: n.data.output_key || 'output',
        position: n.position,
      })),
      edges: edges.map(e => ({
        from_node: e.source,
        to_node: e.target,
        data_map: e.data?.data_map || {},
      })),
      entry_node: entryNode?.id || null,
      exit_node: exitNode?.id || null,
    }
  }

  const handleRun = async () => {
    setError('')
    setRunning(true)
    try {
      const config = buildConfig()
      const res = await runPipelineAdhoc(config, input)
      onResultsReady(res.data)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 260, background: 'var(--bg-1, #fff)',
      borderTop: '1px solid var(--border)', padding: '12px 16px', zIndex: 10,
      display: 'flex', gap: 10, alignItems: 'flex-start',
    }}>
      <textarea
        style={{
          flex: 1, padding: '8px 10px', borderRadius: 8, fontSize: 13,
          border: '1px solid var(--border)', resize: 'none', height: 56,
          background: 'var(--bg-2)', color: 'var(--text-1)',
        }}
        placeholder="Enter input for the pipeline entry node…"
        value={input}
        onChange={e => setInput(e.target.value)}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button onClick={handleRun} disabled={running} style={{
          padding: '8px 20px', borderRadius: 8, background: '#6366f1', color: '#fff',
          border: 'none', cursor: running ? 'not-allowed' : 'pointer', fontWeight: 600,
          fontSize: 13, opacity: running ? 0.7 : 1, whiteSpace: 'nowrap',
        }}>
          {running ? '⏳ Running…' : '▶ Run'}
        </button>
        <button onClick={onClose} style={{
          padding: '5px 10px', borderRadius: 6, background: 'transparent',
          border: '1px solid var(--border)', cursor: 'pointer', fontSize: 12, color: 'var(--text-2)',
        }}>
          Cancel
        </button>
      </div>
      {error && (
        <div style={{ color: '#ef4444', fontSize: 12, padding: '4px 8px', alignSelf: 'center' }}>{error}</div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Save/Load modal
// ---------------------------------------------------------------------------
function SaveLoadModal({ nodes, edges, onClose, onLoad }) {
  const [pipelines, setPipelines] = useState(null)
  const [name, setName] = useState('My Pipeline')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const loadList = useCallback(async () => {
    try {
      const res = await listPipelines()
      setPipelines(res.data)
    } catch { setPipelines([]) }
  }, [])

  useState(() => { loadList() }, [])

  const buildConfig = (id) => ({
    id: id || `pl-${Date.now()}`,
    name,
    nodes: nodes.map(n => ({
      id: n.id,
      name: n.data.name || 'Agent',
      system_prompt: n.data.system_prompt || 'You are a helpful assistant.',
      model: n.data.model || 'llama-3.1-8b-instant',
      max_iterations: n.data.max_iterations ?? 5,
      input_key: n.data.input_key || 'input',
      output_key: n.data.output_key || 'output',
      position: n.position,
    })),
    edges: edges.map(e => ({
      from_node: e.source,
      to_node: e.target,
      data_map: e.data?.data_map || {},
    })),
    entry_node: nodes.find(n => n.data.isEntry)?.id || null,
    exit_node: nodes.find(n => n.data.isExit)?.id || null,
  })

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      await savePipeline(buildConfig())
      setMsg('Saved!')
      loadList()
    } catch (err) {
      setMsg(err.response?.data?.detail ?? err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleLoad = async (id) => {
    try {
      const res = await getPipeline(id)
      onLoad(res.data)
      onClose()
    } catch (err) {
      setMsg(err.response?.data?.detail ?? err.message)
    }
  }

  const handleDelete = async (id) => {
    try {
      await deletePipeline(id)
      loadList()
    } catch { }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-1, #fff)', borderRadius: 12, padding: 24, width: 420,
        maxHeight: '70vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 16 }}>Save / Load Pipeline</div>

        {/* Save section */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>SAVE CURRENT</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              style={{ flex: 1, padding: '7px 10px', borderRadius: 6, border: '1px solid var(--border)', fontSize: 13, background: 'var(--bg-2)', color: 'var(--text-1)' }}
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Pipeline name"
            />
            <button onClick={handleSave} disabled={saving} style={{
              padding: '7px 16px', borderRadius: 6, background: '#6366f1', color: '#fff',
              border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13,
            }}>
              {saving ? '…' : 'Save'}
            </button>
          </div>
          {msg && <div style={{ fontSize: 12, color: msg === 'Saved!' ? '#22c55e' : '#ef4444', marginTop: 6 }}>{msg}</div>}
        </div>

        {/* Load section */}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>SAVED PIPELINES</div>
          {pipelines === null ? (
            <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Loading…</div>
          ) : pipelines.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-2)' }}>No saved pipelines yet.</div>
          ) : (
            pipelines.map(p => (
              <div key={p.id} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0',
                borderBottom: '1px solid var(--border)',
              }}>
                <span style={{ flex: 1, fontSize: 13 }}>{p.name}</span>
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{p.nodes.length} nodes</span>
                <button onClick={() => handleLoad(p.id)} style={{
                  padding: '3px 10px', borderRadius: 6, background: '#6366f1', color: '#fff',
                  border: 'none', cursor: 'pointer', fontSize: 12,
                }}>Load</button>
                <button onClick={() => handleDelete(p.id)} style={{
                  padding: '3px 10px', borderRadius: 6, background: 'transparent',
                  border: '1px solid #ef4444', color: '#ef4444', cursor: 'pointer', fontSize: 12,
                }}>✕</button>
              </div>
            ))
          )}
        </div>

        <button onClick={onClose} style={{
          marginTop: 16, padding: '6px 16px', borderRadius: 6, background: 'transparent',
          border: '1px solid var(--border)', cursor: 'pointer', fontSize: 13, color: 'var(--text-2)',
        }}>Close</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PipelinePage — main component
// ---------------------------------------------------------------------------
let nodeCounter = 0
const newNodeId = () => `node-${++nodeCounter}`

export default function PipelinePage() {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [showRunPanel, setShowRunPanel] = useState(false)
  const [showSaveLoad, setShowSaveLoad] = useState(false)
  const [runResults, setRunResults] = useState(null)
  const reactFlowWrapper = useRef(null)

  // ── Connect two nodes ────────────────────────────────────────────────────
  const onConnect = useCallback(
    (params) => setEdges(eds => addEdge({ ...params, data: { data_map: {} } }, eds)),
    [setEdges]
  )

  // ── Add a new agent node ─────────────────────────────────────────────────
  const addNode = useCallback(() => {
    const id = newNodeId()
    setNodes(ns => [...ns, {
      id,
      type: 'agentNode',
      position: { x: 100 + (ns.length % 4) * 240, y: 80 + Math.floor(ns.length / 4) * 180 },
      data: {
        name: `Agent ${id}`,
        system_prompt: 'You are a helpful assistant.',
        model: DEFAULT_MODELS[0],
        max_iterations: 5,
        input_key: 'input',
        output_key: 'output',
        isEntry: ns.length === 0,   // First node auto-set as entry
        isExit: false,
      },
    }])
  }, [setNodes])

  // ── Update node data ─────────────────────────────────────────────────────
  const updateNodeData = useCallback((nodeId, newData) => {
    setNodes(ns => ns.map(n => n.id === nodeId ? { ...n, data: newData } : n))
    setSelectedNode(prev => prev?.id === nodeId ? { ...prev, data: newData } : prev)
  }, [setNodes])

  // ── Set entry node ───────────────────────────────────────────────────────
  const setEntryNode = useCallback((nodeId) => {
    setNodes(ns => ns.map(n => ({
      ...n,
      data: { ...n.data, isEntry: n.id === nodeId },
    })))
  }, [setNodes])

  // ── Set exit node ────────────────────────────────────────────────────────
  const setExitNode = useCallback((nodeId) => {
    setNodes(ns => ns.map(n => ({
      ...n,
      data: { ...n.data, isExit: n.id === nodeId },
    })))
  }, [setNodes])

  // ── Delete node ──────────────────────────────────────────────────────────
  const deleteNode = useCallback((nodeId) => {
    setNodes(ns => ns.filter(n => n.id !== nodeId))
    setEdges(es => es.filter(e => e.source !== nodeId && e.target !== nodeId))
    setSelectedNode(null)
  }, [setNodes, setEdges])

  // ── Click handler ────────────────────────────────────────────────────────
  const onNodeClick = useCallback((_, node) => setSelectedNode(node), [])
  const onPaneClick = useCallback(() => setSelectedNode(null), [])

  // ── Run results → annotate nodes ─────────────────────────────────────────
  const handleRunResults = useCallback((result) => {
    setRunResults(result)
    setShowRunPanel(false)
    const byId = {}
    for (const r of result.node_results || []) byId[r.node_id] = r
    setNodes(ns => ns.map(n => ({
      ...n,
      data: { ...n.data, runResult: byId[n.id] || null },
    })))
  }, [setNodes])

  // ── Load pipeline ────────────────────────────────────────────────────────
  const handleLoadPipeline = useCallback((config) => {
    const rfNodes = config.nodes.map(n => ({
      id: n.id,
      type: 'agentNode',
      position: n.position || { x: 100, y: 100 },
      data: {
        name: n.name,
        system_prompt: n.system_prompt,
        model: n.model,
        max_iterations: n.max_iterations,
        input_key: n.input_key,
        output_key: n.output_key,
        isEntry: n.id === config.entry_node,
        isExit: n.id === config.exit_node,
        runResult: null,
      },
    }))
    const rfEdges = config.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.from_node,
      target: e.to_node,
      data: { data_map: e.data_map || {} },
    }))
    setNodes(rfNodes)
    setEdges(rfEdges)
    setRunResults(null)
    setSelectedNode(null)
  }, [setNodes, setEdges])

  // ── Clear all ────────────────────────────────────────────────────────────
  const clearCanvas = useCallback(() => {
    setNodes([])
    setEdges([])
    setSelectedNode(null)
    setRunResults(null)
  }, [setNodes, setEdges])

  // ── Remove run result overlays ───────────────────────────────────────────
  const clearResults = useCallback(() => {
    setRunResults(null)
    setNodes(ns => ns.map(n => ({ ...n, data: { ...n.data, runResult: null } })))
  }, [setNodes])

  const entryNodeSet = nodes.some(n => n.data.isEntry)
  const exitNodeSet = nodes.some(n => n.data.isExit)
  const canRun = nodes.length > 0 && entryNodeSet && exitNodeSet

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 48px)', position: 'relative' }}>
      {/* React Flow Canvas */}
      <div ref={reactFlowWrapper} style={{ flex: 1, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={NODE_TYPES}
          fitView
          deleteKeyCode="Delete"
          style={{ background: 'var(--bg-2, #f8fafc)' }}
        >
          <Background color="#cbd5e1" gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeColor={(n) => n.data.isEntry ? '#22c55e' : n.data.isExit ? '#6366f1' : '#94a3b8'}
            style={{ background: 'var(--bg-1)' }}
          />

          {/* Top toolbar */}
          <Panel position="top-left">
            <div style={{
              display: 'flex', gap: 6, padding: '8px 10px',
              background: 'var(--bg-1, #fff)', borderRadius: 10,
              boxShadow: '0 2px 12px rgba(0,0,0,0.1)', border: '1px solid var(--border)',
            }}>
              <button onClick={addNode} style={tbBtn('#6366f1')}>+ Add Node</button>
              <div style={{ width: 1, background: 'var(--border)', margin: '0 2px' }} />
              <button
                onClick={() => { clearResults(); setShowRunPanel(v => !v) }}
                disabled={!canRun}
                style={tbBtn(canRun ? '#22c55e' : '#94a3b8')}
                title={!canRun ? 'Set an entry and exit node first' : ''}
              >
                ▶ Run
              </button>
              <button onClick={() => setShowSaveLoad(true)} style={tbBtn('#3b82f6')}>💾 Save/Load</button>
              <button onClick={clearCanvas} style={tbBtn('#ef4444')}>✕ Clear</button>
            </div>
          </Panel>

          {/* Status badges */}
          <Panel position="top-right">
            <div style={{
              display: 'flex', gap: 8, padding: '8px 12px',
              background: 'var(--bg-1, #fff)', borderRadius: 10,
              boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid var(--border)',
              fontSize: 12,
            }}>
              <span style={{ color: '#64748b' }}>{nodes.length} node{nodes.length !== 1 ? 's' : ''}</span>
              <span style={{ color: '#64748b' }}>•</span>
              <span style={{ color: entryNodeSet ? '#22c55e' : '#ef4444' }}>
                {entryNodeSet ? '✓ entry' : '⚠ no entry'}
              </span>
              <span style={{ color: '#64748b' }}>•</span>
              <span style={{ color: exitNodeSet ? '#6366f1' : '#ef4444' }}>
                {exitNodeSet ? '✓ exit' : '⚠ no exit'}
              </span>
            </div>
          </Panel>

          {/* Run result summary */}
          {runResults && (
            <Panel position="bottom-center">
              <div style={{
                padding: '10px 16px', background: runResults.success ? '#f0fdf4' : '#fef2f2',
                border: `1px solid ${runResults.success ? '#86efac' : '#fca5a5'}`,
                borderRadius: 10, fontSize: 13, maxWidth: 500,
                color: runResults.success ? '#166534' : '#dc2626',
              }}>
                {runResults.success
                  ? <><strong>✓ Pipeline complete</strong> · {(runResults.final_output || '').slice(0, 200)}</>
                  : <><strong>✗ Pipeline failed</strong> · {runResults.error}</>
                }
                <button onClick={clearResults} style={{
                  marginLeft: 12, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14,
                  color: 'inherit',
                }}>✕</button>
              </div>
            </Panel>
          )}

          {/* Empty state hint */}
          {nodes.length === 0 && (
            <Panel position="top-center">
              <div style={{
                marginTop: 80, padding: '24px 32px', textAlign: 'center',
                background: 'var(--bg-1, #fff)', borderRadius: 12,
                border: '2px dashed var(--border)', color: 'var(--text-2)',
                pointerEvents: 'none',
              }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>🔗</div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Visual Pipeline Builder</div>
                <div style={{ fontSize: 12 }}>
                  Click <strong>+ Add Node</strong> to create agent nodes, then drag between handles to connect them.
                </div>
              </div>
            </Panel>
          )}
        </ReactFlow>

        {/* Run panel */}
        {showRunPanel && (
          <RunPanel
            nodes={nodes}
            edges={edges}
            onClose={() => setShowRunPanel(false)}
            onResultsReady={handleRunResults}
          />
        )}
      </div>

      {/* Right config panel */}
      {selectedNode && (
        <NodeConfigPanel
          node={selectedNode}
          onChange={updateNodeData}
          onSetEntry={setEntryNode}
          onSetExit={setExitNode}
          onDelete={deleteNode}
        />
      )}

      {/* Save/Load modal */}
      {showSaveLoad && (
        <SaveLoadModal
          nodes={nodes}
          edges={edges}
          onClose={() => setShowSaveLoad(false)}
          onLoad={handleLoadPipeline}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Toolbar button style helper
// ---------------------------------------------------------------------------
function tbBtn(bg) {
  return {
    padding: '6px 12px', borderRadius: 7, background: bg, color: '#fff',
    border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
    opacity: 1, transition: 'opacity 0.15s',
  }
}
