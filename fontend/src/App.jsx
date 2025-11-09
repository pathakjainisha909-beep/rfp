import { useState, useEffect, useRef } from 'react'
import BankSelector from './components/BankSelector'
import LogPanel from './components/LogPanel'
import ResultsTable from './components/ResultsTable'

function App() {
  const [banks, setBanks] = useState([])
  const [selectedBank, setSelectedBank] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)

  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  const fetchBanks = async (retryCount = 0) => {
    try {
      const response = await fetch('http://localhost:8000/api/banks')
      const data = await response.json()

      if (data.banks && data.banks.length > 0) {
        setBanks(data.banks)
        addLog('success', `Loaded ${data.banks.length} bank(s)`)
      } else if (retryCount < 3) {
        setTimeout(() => fetchBanks(retryCount + 1), 2000)
      } else {
        addLog('error', 'No banks found in config')
      }
    } catch {
      if (retryCount < 3) {
        addLog('warning', `Retrying to fetch banks... (${retryCount + 1}/3)`)
        setTimeout(() => fetchBanks(retryCount + 1), 2000)
      } else {
        addLog('error', 'Failed to fetch banks. Check backend.')
      }
    }
  }

  useEffect(() => {
    setTimeout(() => fetchBanks(), 1000)
  }, [])

  useEffect(() => {
    connectWebSocket()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    }
  }, [])

  const connectWebSocket = () => {
    try {
      const ws = new WebSocket('ws://localhost:8000/ws')

      ws.onopen = () => {
        setWsConnected(true)
        addLog('success', 'Connected to server')
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'log') addLog(message.level, message.message)
          else if (message.type === 'progress')
            addLog('progress', `${message.stage}: ${message.current}/${message.total} - ${message.message}`)
          else if (message.type === 'pdf_status')
            addLog(message.status === 'filtered' ? 'success' : 'warning', `${message.pdf_name}: ${message.reason}`)
          else if (message.type === 'completion') {
            setIsRunning(false)
            addLog('success', 'Process completed. Loading results.')
            fetchResults()
          }
        } catch {}
      }

      ws.onerror = () => setWsConnected(false)

      ws.onclose = () => {
        setWsConnected(false)
        if (!reconnectTimeoutRef.current) {
          addLog('warning', 'Reconnecting to server...')
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null
            connectWebSocket()
          }, 3000)
        }
      }

      wsRef.current = ws
    } catch {
      setWsConnected(false)
    }
  }

  const addLog = (level, message) => {
    setLogs(prev => [...prev, { level, message, timestamp: new Date().toLocaleTimeString() }])
  }

  const fetchResults = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/results')
      const data = await response.json()
      setResults(data.results || [])
      setShowResults(true)
      addLog('info', `Found ${data.results?.length || 0} processed tenders`)
    } catch {
      addLog('error', 'Failed to fetch results')
    }
  }

  const handleStart = async () => {
    if (!selectedBank) return
    if (!wsConnected) return
    setIsRunning(true)
    setLogs([])
    setShowResults(false)
    setResults([])
    addLog('info', `Starting automation for ${selectedBank}...`)
    try {
      const response = await fetch('http://localhost:8000/api/start', { method: 'POST' })
      if (!response.ok) throw new Error('Failed to start automation')
      addLog('success', 'Automation started')
    } catch (err) {
      addLog('error', `Failed to start: ${err.message}`)
      setIsRunning(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#D9EEF2] text-[#2C4A66] font-light">

      <header className="w-full bg-white border-b border-[#c8dce2] py-4">
        <div className="max-w-7xl mx-auto px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/selectai_logo.png" alt="Select AI" className="h-10 w-auto" />
            <span className="tracking-wide text-xl font-semibold text-[#1B2B44]"></span>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-sm px-3 py-1 rounded-md border border-[#9fb7c4]/70 text-[#1B2B44] bg-white flex items-center gap-2">
              <div className={`w-2.5 h-2.5 rounded-full ${wsConnected ? 'bg-[#53C3D0]' : 'bg-red-500'}`}></div>
              {wsConnected ? 'Connected' : 'Disconnected'}
            </div>

            <BankSelector banks={banks} selected={selectedBank} onChange={setSelectedBank} disabled={isRunning} />

            <button
              onClick={handleStart}
              disabled={isRunning || !selectedBank || !wsConnected}
              className="px-6 py-2.5 bg-[#1B2B44] text-white rounded-md text-sm font-medium disabled:bg-gray-400"
            >
              {isRunning ? 'RUNNING...' : 'START'}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-10 grid grid-cols-4 gap-8">
        <div className="col-span-1 max-w-[420px]">
          <LogPanel logs={logs} />
        </div>

        <div className="col-span-3">
          {showResults && results.length > 0 && (
            <ResultsTable results={results} />
          )}
        </div>
      </main>

    </div>
  )
}

export default App
