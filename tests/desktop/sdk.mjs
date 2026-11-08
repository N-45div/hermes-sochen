// The parts of @hermes/plugin-sdk the plugin uses, as stand-ins.
export const PANES_AREA = 'panes'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const PALETTE_AREA = 'palette'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }

export function atom(initial) {
  let value = initial
  return { get: () => value, set: next => { value = next } }
}
export const useValue = store => store.get()

export const Button = props => ({ type: 'Button', props })
export const StatusDot = props => ({ type: 'StatusDot', props })

export const host = {
  notes: [],
  routes: [],
  notify(note) { this.notes.push(note) },
  navigate(path) { this.routes.push(path) }
}
