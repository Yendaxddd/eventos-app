# 🧪 Eventos App - Testing Guide

This guide explains how to test the core features of the Eventos app, including the new debug terminal.

## 🚀 How to Run the App

1.  **Open a terminal** in the `eventos-app` directory.
2.  **Run the start script**:
    ```bash
    ./start.sh
    ```
3.  The script will start the backend server and open the frontend in your browser.

## 🎮 How to Test Core Features

1.  **Open the App**: The `start.sh` script should open `frontend/index.html` in your browser.
2.  **Join a Campaign**:
    *   Enter a username (e.g., `TestPlayer`).
    *   Enter a campaign ID (e.g., `test_campaign`) or leave it empty to use the default.
    *   Click "Join Campaign". You should see the main game interface.
3.  **Trigger a QTE**:
    *   Click the "Test QTE" button in the "Actions" panel on the right.
    *   A QTE will appear in the center of the screen with a countdown timer.
4.  **Respond to the QTE**:
    *   Use the on-screen buttons (EVADE, PARRY, SAVE) or keyboard shortcuts (Q/A, W/S, E/D) to respond.
    *   Check the combat log for the result of your action.
    *   If you fail, your HP will decrease.

## 🐛 How to Use the Debug Terminal

The debug terminal gives you powerful tools to test and control the game state in real-time.

1.  **Open the Terminal**: Click the bug icon (🐛) in the bottom-right corner of the screen.
2.  **Available Commands**: Type `help` in the terminal to see a list of available commands.

### Key Debug Commands:

*   `qte [difficulty]`: Trigger a QTE of a specific difficulty (e.g., `qte hard`).
*   `damage [amount]`: Simulate taking damage (e.g., `damage 50`).
*   `heal [amount]`: Heal your character (e.g., `heal 30`).
*   `stats`: Display your current player and connection stats.
*   `clear`: Clear the terminal window.
*   `ws`: Check the WebSocket connection status.

## 🚨 Admin Controls

The admin buttons from the original Discord bot have been integrated into the debug terminal for a cleaner interface. Here's how to use them:

*   **Trigger QTEs**: Use the `qte` command as described above.
*   **Adjust Game Values**: Future commands like `set_hp` or `set_bf_chance` can be added to the `processDebugCommand` function in `index.html`.
*   **Manage Players**: Commands like `kick` or `mute` can be added.

This approach keeps the main UI clean for players while giving you full control through the debug terminal.

## ✅ What to Test

*   **Connectivity**: Can you join a campaign?
*   **QTE Flow**: Can you trigger and respond to QTEs?
*   **HP System**: Does your HP decrease on failure and increase with `heal`?
*   **REVENGE Mode**: Does it activate at 20% HP?
*   **Debug Commands**: Do the `qte`, `damage`, and `heal` commands work?
*   **Responsiveness**: Does the app work on different screen sizes?

Happy testing! 🚀
