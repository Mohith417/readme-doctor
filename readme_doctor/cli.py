import click
from readme_doctor.fetcher import fetch_repo_data

@click.command()
@click.argument('repo_url')
def main(repo_url):
    """README Doctor - Analyze any GitHub repo's README"""
    click.echo(f"\n🔍 Fetching repo: {repo_url}\n")
    
    data = fetch_repo_data(repo_url)
    
    if data is None:
        click.echo("❌ Could not fetch repo. Check the URL and try again.")
        return
    
    click.echo(f"✅ Repo: {data['name']}")
    click.echo(f"📝 Description: {data['description']}")
    click.echo(f"⭐ Stars: {data['stars']}")
    click.echo(f"💻 Language: {data['language']}")
    click.echo(f"\n📄 README Preview (first 500 chars):\n")
    click.echo(data['readme'][:500])

if __name__ == '__main__':
    main()