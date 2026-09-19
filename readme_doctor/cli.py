import click
from readme_doctor.fetcher import fetch_repo_data
from readme_doctor.analyzer import analyze_readme
from readme_doctor.scorer import parse_score, get_grade

@click.command()
@click.argument('repo_url')
def main(repo_url):
    """README Doctor - Analyze any GitHub repo's README using AI"""
    
    click.echo(f"\n🔍 Fetching repo: {repo_url}\n")
    
    data = fetch_repo_data(repo_url)
    
    if data is None:
        click.echo("❌ Could not fetch repo. Check the URL and try again.")
        return
    
    click.echo(f"✅ Repo: {data['name']}")
    click.echo(f"📝 Description: {data['description']}")
    click.echo(f"⭐ Stars: {data['stars']}")
    click.echo(f"💻 Language: {data['language']}")
    
    click.echo(f"\n🤖 Analyzing README with AI...\n")
    
    analysis = analyze_readme(data['readme'])
    
    if analysis is None:
        click.echo("❌ AI analysis failed. Check your API key.")
        return
    
    score = parse_score(analysis)
    grade, grade_msg = get_grade(score)
    
    click.echo(f"{'='*50}")
    click.echo(f"📊 README HEALTH REPORT: {data['name']}")
    click.echo(f"{'='*50}")
    click.echo(f"🎯 Score: {score}/100  |  Grade: {grade}  |  {grade_msg}")
    click.echo(f"{'='*50}\n")
    click.echo(analysis)

if __name__ == '__main__':
    main()