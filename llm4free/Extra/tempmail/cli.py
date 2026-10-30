"""
Command-line interface for temporary email generation using SwiftCLI
"""

import sys
import time
from typing import Optional, cast

from rich.console import Console

try:
    try:
        from llm4free.swiftcli import CLI, option, argument
    except Exception:
        raise ImportError("swiftcli is required for this CLI")
except Exception:
    class CLI:
        def __init__(self,*a,**k): pass
        def command(self,*a,**k): return lambda f: f
        def run(self): pass
    option = lambda *a, **k: (lambda f: f)
    argument = lambda *a, **k: (lambda f: f)

from .base import TempMailProvider, get_provider

# Initialize console for rich output
console = Console()

# Create CLI app
app = CLI(name="tempmail", help="Temporary Email CLI Tool", version="1.0.0")


@app.command()
@option(
    "--wait",
    "-w",
    type=int,
    default=10,
    help="Wait time in seconds between checking for new messages",
)
@option(
    "--output",
    "-o",
    type=str,
    choices=["simple", "detailed"],
    default="simple",
    help="Output format",
)
@option(
    "--provider",
    "-p",
    type=str,
    choices=["mailtm", "tempmailio"],
    default="mailtm",
    help="Email provider to use",
)
def monitor(wait: int = 10, output: str = "simple", provider: str = "mailtm"):
    """
    Create and monitor a temporary email account

    Continuously checks for new messages and displays them in the terminal.
    Press Ctrl+C to exit and delete the account.
    """
    # Create a new email
    mail = cast(TempMailProvider, get_provider(provider_name=provider))

    if hasattr(mail, "auto_create"):
        mail = cast(TempMailProvider, get_provider(provider_name=provider, async_provider=False))
        mail.create_account()
    else:
        success = mail.create_account()
        if not success:
            console.print("[red]Failed to create temporary email account.[/red]")
            sys.exit(1)

    console.print("[yellow]Temporary email address CLI[/yellow]")
    console.print(f"[cyan]EMAIL: {mail.email}[/cyan]")
    console.print(f"Account ID: {mail.account_id}")
    console.print("Press Ctrl+C to exit and delete the account")

    try:
        while True:
            console.print(f"Checking for new messages... ({time.strftime('%H:%M:%S')})")
            new_messages = mail.check_new_messages()

            if new_messages:
                console.print(f"New messages: {len(new_messages)}")
                console.print("-" * 40)

                for msg in new_messages:
                    console.print(f"From: {msg['from']}")
                    console.print(f"Subject: {msg['subject']}")

                    if output == "detailed":
                        console.print(f"Body: {msg['body']}")
                        console.print(f"Has attachments: {msg['hasAttachments']}")
                        console.print(f"Created at: {msg['createdAt']}")

                    console.print("[magenta]" + "-" * 40 + "[/magenta]")

            time.sleep(wait)

    except KeyboardInterrupt:
        console.print("\nCtrl+C pressed. Exiting program and deleting account...")
        if mail.delete_account():
            console.print("[red]--Account deleted--[/red]")
        else:
            console.print("[red]--Failed to delete account--[/red]")


@app.command()
@option(
    "--provider",
    "-p",
    type=str,
    choices=["mailtm", "tempmailio"],
    default="mailtm",
    help="Email provider to use",
)
def create(provider: str = "mailtm"):
    """
    Create a temporary email account and display its details

    Creates a new temporary email account and displays the email address.
    The account will remain active until manually deleted.
    """
    mail = cast(TempMailProvider, get_provider(provider_name=provider))

    if hasattr(mail, "auto_create"):
        mail = cast(TempMailProvider, get_provider(provider_name=provider, async_provider=False))
        mail.create_account()
    else:
        success = mail.create_account()
        if not success:
            console.print("[red]Failed to create temporary email account.[/red]")
            sys.exit(1)

    console.print("[yellow]Temporary Email Created[/yellow]")
    console.print(f"[cyan]EMAIL: {mail.email}[/cyan]")
    console.print(f"Account ID: {mail.account_id}")
    console.print("Use 'tempmail monitor' to check for messages")


@app.command()
@option("--email", "-e", type=str, required=True, help="Email address to check")
@option("--account-id", "-a", type=str, required=True, help="Account ID for the email")
@option(
    "--provider",
    "-p",
    type=str,
    choices=["mailtm", "tempmailio"],
    default="mailtm",
    help="Email provider to use",
)
@option(
    "--output",
    "-o",
    type=str,
    choices=["simple", "detailed"],
    default="simple",
    help="Output format",
)
def check(email: str, account_id: str, provider: str = "mailtm", output: str = "simple"):
    """
    Check messages for an existing temporary email account

    Retrieves and displays messages for an existing temporary email account.
    Requires the email address and account ID.
    """
    mail = cast(TempMailProvider, get_provider(provider_name=provider))
    mail.email = email
    mail.account_id = account_id

    # Try to get token if needed
    if hasattr(mail, "get_token"):
        mail.get_token()

    console.print(f"[cyan]Checking messages for: {email}[/cyan]")

    try:
        messages = mail.get_messages()

        if not messages:
            console.print("[yellow]No messages found[/yellow]")
            return

        console.print(f"Found {len(messages)} messages:")
        console.print("-" * 40)

        for msg in messages:
            console.print(f"From: {msg['from']}")
            console.print(f"Subject: {msg['subject']}")

            if output == "detailed":
                console.print(f"Body: {msg['body']}")
                console.print(f"Has attachments: {msg['hasAttachments']}")
                console.print(f"Created at: {msg['createdAt']}")

            console.print("[magenta]" + "-" * 40 + "[/magenta]")

    except Exception as e:
        console.print(f"[red]Error checking messages: {str(e)}[/red]")


@app.command()
@option("--email", "-e", type=str, required=True, help="Email address to delete")
@option("--account-id", "-a", type=str, required=True, help="Account ID for the email")
@option(
    "--provider",
    "-p",
    type=str,
    choices=["mailtm", "tempmailio"],
    default="mailtm",
    help="Email provider to use",
)
def delete(email: str, account_id: str, provider: str = "mailtm"):
    """
    Delete an existing temporary email account

    Deletes a temporary email account using the provided email address and account ID.
    """
    mail = cast(TempMailProvider, get_provider(provider_name=provider))
    mail.email = email
    mail.account_id = account_id

    # Try to get token if needed
    if hasattr(mail, "get_token"):
        mail.get_token()

    console.print(f"[yellow]Deleting account: {email}[/yellow]")

    try:
        success = mail.delete_account()
        if success:
            console.print("[green]Account successfully deleted[/green]")
        else:
            console.print("[red]Failed to delete account[/red]")
    except Exception as e:
        console.print(f"[red]Error deleting account: {str(e)}[/red]")


def main():
    """Main CLI function for tempmail"""
    try:
        app.run()
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
