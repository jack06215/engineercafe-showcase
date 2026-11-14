# src/store

Global Zustand stores. State only one feature uses belongs in that feature's
`store/`; state that should survive a reload or be shareable as a link
belongs in the URL, as a route's search params.
