# Security deployment changes

Install requirements-security.txt in the environment running pilot tools. XML test reports now reject entity expansion. Git archive extraction uses argument lists, and the shared command helper rejects shell strings. These tools execute tests and setup code from cloned repositories by design; run those workloads in an isolated sandbox.
