export default function Browse(){
  return (
    <div className="container py-8 space-y-6">
      <h1 className="text-2xl font-semibold">Browse</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <a href="/courses" className="card p-6">
          <div className="text-lg font-medium">My Courses</div>
          <p className="text-muted">View courses you’re learning.</p>
        </a>
        <a href="/upload" className="card p-6">
          <div className="text-lg font-medium">Upload Materials</div>
          <p className="text-muted">Add PDFs, docs, or YouTube links.</p>
        </a>
      </div>
    </div>
  )
}
