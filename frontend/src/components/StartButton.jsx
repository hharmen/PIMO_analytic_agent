import { ArrowIcon } from './Icons'

export default function StartButton({ children = 'Начать проверку', size = 'lg', variant = 'solid', className = '', ...rest }) {
  return (
    <button type="button" className={`cta-btn cta-btn-${size} cta-btn-${variant} ${className}`.trim()} {...rest}>
      <span>{children}</span>
      <ArrowIcon />
    </button>
  )
}
