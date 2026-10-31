import { useCallback, useEffect, useRef, useState } from 'react'

const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

export function useInView(options = {}) {
  const ref = useRef(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return undefined

    if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
      setInView(true)
      return undefined
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.disconnect()
        }
      },
      { threshold: 0.2, rootMargin: '0px 0px -60px 0px', ...options },
    )
    observer.observe(node)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return [ref, inView]
}

export function useCountUp(target, { duration = 1200, decimals = 0, start = true } = {}) {
  const [reduced] = useState(prefersReducedMotion)
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!start || reduced) return undefined

    let frame
    const startedAt = performance.now()
    const tick = (now) => {
      const progress = Math.min((now - startedAt) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(target * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration, start, reduced])

  return Number((reduced ? target : value).toFixed(decimals))
}

export function useHashRoute(routes, fallback) {
  const read = () => {
    const hash = window.location.hash.replace(/^#\/?/, '')
    return routes.includes(hash) ? hash : fallback
  }

  const [route, setRoute] = useState(read)

  useEffect(() => {
    const onChange = () => setRoute(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const navigate = useCallback(
    (next, { replace = false } = {}) => {
      const url = next === fallback ? window.location.pathname : `#/${next}`
      if (replace) window.history.replaceState(null, '', url)
      else window.history.pushState(null, '', url)
      setRoute(next)
    },
    [fallback],
  )

  return [route, navigate]
}

export function useScreenTransition(route, duration = 320) {
  const [shown, setShown] = useState(route)
  const [phase, setPhase] = useState('enter')

  useEffect(() => {
    if (route === shown) return undefined

    const reduced = prefersReducedMotion()
    const exitFrame = requestAnimationFrame(() => {
      if (!reduced) setPhase('exit')
    })
    const timer = window.setTimeout(() => {
      setShown(route)
      setPhase('enter')
      window.scrollTo(0, 0)
    }, reduced ? 0 : duration)
    return () => {
      cancelAnimationFrame(exitFrame)
      window.clearTimeout(timer)
    }
  }, [route, shown, duration])

  return [shown, phase]
}
