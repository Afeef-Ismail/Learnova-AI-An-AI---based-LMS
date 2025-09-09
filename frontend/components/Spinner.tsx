export function Spinner({ size = 20 }: { size?: number }){
  const s = `${size}px`
  return (
    <span className="inline-block align-middle border-2 border-white/30 border-t-white/90 rounded-full animate-spin" style={{ width: s, height: s }} />
  )
}
