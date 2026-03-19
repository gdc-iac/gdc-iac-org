# kpt

## Description
GDC composite application

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/PKG_PATH[@VERSION] kpt`
Details: https://kpt.dev/reference/cli/pkg/get/

### View package content
`kpt pkg tree kpt`
Details: https://kpt.dev/reference/cli/pkg/tree/

### Apply the package
```
kpt live init kpt
kpt live apply kpt --reconcile-timeout=2m --output=table
```
Details: https://kpt.dev/reference/cli/live/
