function BankSelector({ banks, selected, onChange, disabled }) {
  return (
    <div className="relative">
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="appearance-none border border-[#9fb7c4] bg-white rounded-md px-4 py-2 text-[#1B2B44] text-sm focus:ring-2 focus:ring-[#53C3D0] outline-none min-w-[200px] disabled:bg-[#dfe8eb] disabled:text-[#7a8c96] disabled:cursor-not-allowed"
      >
        <option value="">Select</option>
        {banks.map(bank => (
          <option key={bank.id} value={bank.id}>
            {bank.name}
          </option>
        ))}
      </select>

      <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-[#6b8799]">
        <svg className="h-5 w-5" viewBox="0 0 20 20">
          <path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/>
        </svg>
      </div>
    </div>
  )
}

export default BankSelector
