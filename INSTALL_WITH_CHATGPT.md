# Install this app with your dot

You are installing an existing application on the owner's connected Mac. This is not a request to build a replacement app.

1. Read README.md, AGENTS.md, HANDOVER.md, SECRETS_REQUIRED.md and DOT_INSTRUCTIONS.md.
2. Confirm the Mac is connected and available to you. A cloud-only chat cannot install on an unconnected Mac.
3. Obtain the public source ZIP from https://github.com/handmadeheroes/research-desk or clone that repository. No GitHub account is needed.
4. Use a dedicated folder. Inspect the scripts. Check existing installations and port 8401 before starting another instance.
5. Prefer native installation when Python 3.11+ and Node 22+ exist. Otherwise use Docker Desktop if already installed and running. Explain missing prerequisites; do not silently change another app or reuse its database.
6. Run scripts/install.sh (native) or scripts/install.sh --docker (Docker).
7. Keep the generated owner password and local credentials private. Help the owner enter the password in the local login form. Never send credentials to GitHub, this repository, a remote website or an external message.
8. Start the app, verify /health, sign in and check all six cards.
9. Read the local agent tool list with scripts/agent.sh tools. Save and retrieve a clearly labelled setup-test note; archive it afterward. Check that the audit log attributes these actions to Dot.
10. Install or reference integrations/dot/SKILL.md through the supported local-skill workflow in this ChatGPT client. Test access rather than assuming that an enabled computer connection automatically registers tools.
11. Help the owner add their own Finnhub key in the local Settings form if they want automatic US stock quotes. Do not ask them to paste the key into chat. Other markets can use manual prices.
12. Ask the owner to choose the research export/file location. Preview it, select a small representative batch and verify original files, Markdown, dates and citations before the complete import.
13. Verify a backup and restore into a separate empty data directory. Offer auto-start at login using scripts/install-service.sh after the foreground process is stopped.
14. Report the local app URL, selected installation mode, data location, backup location, working integrations and remaining account connections.

The app is local-first. Connecting sources, importing personal history, enabling off-device backups and connecting the owner's actual dot need their local files/accounts. The source repository contains none of those credentials or personal data.
