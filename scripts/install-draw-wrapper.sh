#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="${repo_dir}/venv/bin/python"
install_dir="${HOME}/.local/bin"
wrapper_path="${install_dir}/draw"

if [[ ! -x "${venv_python}" ]]; then
  echo "Missing virtualenv Python at ${venv_python}" >&2
  echo "Create it first, then run: python3 -m venv venv" >&2
  exit 1
fi

"${venv_python}" -m pip install -e "${repo_dir}"

mkdir -p "${install_dir}"
cat > "${wrapper_path}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

export AWS_DIAGRAM_HOME="${repo_dir}"
exec "${repo_dir}/venv/bin/draw" "\$@"
EOF
chmod +x "${wrapper_path}"

echo "Installed ${wrapper_path}"
case ":\${PATH}:" in
  *":${install_dir}:"*) ;;
  *)
    echo "Add this to your shell profile if draw is not found:"
    echo "  export PATH=\"${install_dir}:\$PATH\""
    ;;
esac
