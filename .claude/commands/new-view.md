# Create a New Frontend View

Create a new frontend view for DeviceKit. The user will provide: **$ARGUMENTS**

## Steps

1. **Create the view component** at `frontend/src/views/<Name>.jsx` following the project's conventions:

```jsx
import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
// Import icons from lucide-react as needed
import { api } from '../api'

export default function <Name>() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      // API calls here
    } catch (e) {
      console.error('Failed to fetch:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="border-b border-main px-8 py-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Title</h1>
          <p className="text-xs text-zinc-500 mt-1">Subtitle</p>
        </div>
      </div>
      {/* Content */}
      <div className="p-8">
        {loading ? (
          <p className="text-zinc-500 text-sm">Loading...</p>
        ) : (
          <div>{/* Main content */}</div>
        )}
      </div>
    </div>
  )
}
```

Reference existing views in `frontend/src/views/` for styling conventions:
- Use Tailwind CSS classes exclusively (no inline styles)
- Dark theme: `bg-black`, `bg-zinc-900`, `border-main`, `text-zinc-400`, `text-zinc-500`
- Accent colors: `emerald` for success, `red` for errors, `blue` for active/running, `amber` for warnings
- Tables: `text-[11px]`, `font-mono`, uppercase headers, `border-main` borders
- Cards: `bg-zinc-900 border border-main rounded-lg`
- Buttons: `bg-white text-black` for primary, `bg-zinc-800 border border-main` for secondary
- Status badges: small rounded pills with colored backgrounds
- Icons from `lucide-react`, sized `w-4 h-4` or `w-3 h-3`

2. **Add the route in `frontend/src/App.jsx`**:
   - Import the new view component at the top with the other imports
   - Add a `<Route>` inside the `<Routes>` block
   - Add a nav item to the appropriate section in `navSections` (Management or Engineering)
   - Pick an appropriate icon from the lucide-react imports (add new import if needed)

3. **Add API methods in `frontend/src/api.js`** if not already present:
   - Add methods the view needs under a new comment section
   - Follow the existing `request()` helper pattern

4. **Verify** by reading back App.jsx to confirm the route and nav item are correct.
