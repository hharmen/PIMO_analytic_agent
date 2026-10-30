import { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import Landing from './screens/Landing'
import InputScreen from './screens/InputScreen'
import AnalysisScreen from './screens/AnalysisScreen'
import ReportScreen from './screens/ReportScreen'
import { DEMO_REPORT } from './data'
import { useHashRoute, useScreenTransition } from './hooks'
import './App.css'

const ROUTES = ['landing', 'input', 'analysis', 'report']

export default function App() {
  const [route, navigate] = useHashRoute(ROUTES, 'landing')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [report, setReport] = useState(null)

  const hasInput = text.trim().length > 0 || Boolean(file)

  useEffect(() => {
    if (route === 'analysis' && !hasInput) navigate('input', { replace: true })
    if (route === 'report' && !report) navigate(hasInput ? 'input' : 'landing', { replace: true })
  }, [route, hasInput, report, navigate])

  const [screen, phase] = useScreenTransition(route)

  const handleAnalysisComplete = useCallback(() => {
    setReport(DEMO_REPORT)
    navigate('report', { replace: true })
  }, [navigate])

  function restart() {
    setText('')
    setFile(null)
    setReport(null)
    navigate('input')
  }

  return (
    <div className="app">
      <Header route={screen} onNavigate={navigate} />

      <main className={`screen screen-${screen} is-${phase}`} key={screen}>
        {screen === 'landing' && <Landing onStart={() => navigate('input')} />}

        {screen === 'input' && (
          <InputScreen
            text={text}
            onTextChange={setText}
            file={file}
            onFileChange={setFile}
            onSubmit={() => {
              setReport(null)
              navigate('analysis')
            }}
            onBack={() => navigate('landing')}
          />
        )}

        {screen === 'analysis' && hasInput && <AnalysisScreen onComplete={handleAnalysisComplete} />}

        {screen === 'report' && report && (
          <ReportScreen report={report} onEdit={() => navigate('input')} onRestart={restart} />
        )}
      </main>

      <footer className="footer container">
        <span>Рискоскоп</span>
        <span>Учебный проект · Сервис не заменяет консультацию специалиста</span>
      </footer>
    </div>
  )
}
