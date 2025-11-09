function ResultsTable({ results }) {
  const handleDownload = async (downloadUrl, tenderName) => {
    try {
      const response = await fetch(`http://localhost:8000${downloadUrl}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${tenderName}_forms.zip`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      alert('Download failed')
    }
  }

  return (
    <div className="bg-white border border-[#c8dce2] rounded-lg shadow-sm">
      <div className="px-6 py-4 border-b border-[#c8dce2] bg-white">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[#1B2B44]">Extracted Tenders</h2>
          <span className="px-3 py-1 bg-[#E2F4F6] text-[#1B2B44] text-sm font-medium rounded-full">
            {results.length} items
          </span>
        </div>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-[#2C4A66]">
          <thead className="bg-[#E2F4F6] border-b border-[#c8dce2]">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase">Tender Name</th>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase">Description</th>
              <th className="px-6 py-3 text-left text-xs font-bold uppercase">Deadline</th>
              <th className="px-6 py-3 text-center text-xs font-bold uppercase">Forms</th>
              <th className="px-6 py-3 text-center text-xs font-bold uppercase">Download</th>
            </tr>
          </thead>

          <tbody>
            {results.map((r, i) => (
              <tr key={i} className="hover:bg-[#F3FAFB]">
                <td className="px-6 py-4 text-sm font-medium">{r.tender_name}</td>
                <td className="px-6 py-4 text-sm">{r.description}</td>
                <td className="px-6 py-4 text-sm font-semibold text-[#53C3D0]">{r.last_date}</td>
                <td className="px-6 py-4 text-center text-sm">{r.forms_count}</td>
                <td className="px-6 py-4 text-center">
                  <button
                    onClick={() => handleDownload(r.download_url, r.tender_name)}
                    className="px-4 py-2 text-sm bg-[#1B2B44] text-white rounded-md"
                  >
                    Download ZIP
                  </button>
                </td>
              </tr>
            ))}
          </tbody>

        </table>
      </div>
    </div>
  )
}

export default ResultsTable
