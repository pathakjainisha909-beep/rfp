import { useEffect, useRef } from 'react'

function LogPanel({ logs }) {
  const logEndRef = useRef(null)

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const getLogStyle = (level) => {
    switch (level) {
      case 'success': 
        return {
          icon: '✓',
          bgColor: 'bg-green-100',
          textColor: 'text-green-700',
          borderColor: 'border-l-green-500'
        }
      case 'error': 
        return {
          icon: '✗',
          bgColor: 'bg-red-100',
          textColor: 'text-red-700',
          borderColor: 'border-l-red-500'
        }
      case 'warning': 
        return {
          icon: '⚠',
          bgColor: 'bg-yellow-100',
          textColor: 'text-yellow-700',
          borderColor: 'border-l-yellow-500'
        }
      case 'progress': 
        return {
          icon: '→',
          bgColor: 'bg-[#E2F4F6]',
          textColor: 'text-[#2C4A66]',
          borderColor: 'border-l-[#53C3D0]'
        }
      default: 
        return {
          icon: '•',
          bgColor: 'bg-white',
          textColor: 'text-[#2C4A66]',
          borderColor: 'border-l-[#9fb7c4]'
        }
    }
  }

  return (
    <div className="bg-white border border-[#c8dce2] rounded-lg shadow-sm flex flex-col" style={{ height: '600px' }}>
      <div className="bg-white px-5 py-3 border-b border-[#c8dce2]">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold tracking-wide text-[#1B2B44]"></span>
          <span className="text-xs text-[#6b8799]"></span>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-hide">
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#6b8799]">
            No activity yet
          </div>
        ) : (
          logs.map((log, index) => {
            const style = getLogStyle(log.level)
            return (
              <div
                key={index}
                className={`${style.bgColor} ${style.borderColor} border-l-4 rounded-r-lg p-3`}
              >
                <div className="flex items-start gap-3">
                  <span className={`flex-shrink-0 font-bold text-lg ${style.textColor}`}>
                    {style.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className={`break-words text-sm ${style.textColor}`}>
                      {log.message}
                    </p>
                    <span className="text-xs text-[#9fb7c4] mt-1 block">{log.timestamp}</span>
                  </div>
                </div>
              </div>
            )
          })
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  )
}

export default LogPanel
