import click
from readme_doctor.fetcher import fetch_repo_data
from readme_doctor.analyzer import analyze_readme, generate_readme
from readme_doctor.scorer import parse_score, get_grade

def colorize_score(score):
    if score is None:
        return click.style("N/A", fg="white")
    if score >= 75:
        return click.style(f"{score}/100", fg="green", bold=True)
    elif score >= 50:
        return click.style(f"{score}/100", fg="yellow", bold=True)
    else:
        return click.style(f"{score}/100", fg="red", bold=True)

def colorize_analysis(analysis_text):
    lines = analysis_text.split('\n')
    output = []
    for line in lines:
        if line.startswith('SCORE:'):
            output.append(click.style(line, fg="cyan", bold=True))
        elif line.startswith('SUMMARY:'):
            output.append(click.style(line, fg="white", bold=True))
        elif line.startswith('ISSUES:'):
            output.append(click.style(line, fg="red", bold=True))
        elif line.startswith('SUGGESTIONS:'):
            output.append(click.style(line, fg="green", bold=True))
        elif line.startswith('- ') and 'ISSUES' in '\n'.join(output[-10:]):
            output.append(click.style(line, fg="red"))
        elif line.startswith('- '):
            output.append(click.style(line, fg="green"))
        else:
            output.append(line)
    return '\n'.join(output)

@click.command()
@click.argument('repo_url')
@click.option('--generate', is_flag=True, help='Generate an improved README')
@click.option('--score-only', is_flag=True, help='Show only the score')
def main(repo_url, generate, score_only):
    """README Doctor - Analyze any GitHub repo's README using AI"""
    
    click.echo(f"\n🔍 Fetching repo: {click.style(repo_url, fg='cyan')}\n")
    
    data = fetch_repo_data(repo_url)
    
    if data is None:
        click.echo(click.style("❌ Could not fetch repo. Check the URL and try again.", fg="red"))
        return
    
    click.echo(f"✅ Repo: {click.style(data['name'], fg='cyan', bold=True)}")
    click.echo(f"📝 Description: {data['description']}")
    click.echo(f"⭐ Stars: {click.style(str(data['stars']), fg='yellow')}")
    click.echo(f"💻 Language: {data['language']}")

    if generate:
        click.echo(f"\n✨ {click.style('Generating improved README...', fg='cyan')}\n")
        new_readme = generate_readme(data)
        if new_readme is None:
            click.echo(click.style("❌ README generation failed.", fg="red"))
            return
        filename = f"{data['name']}_improved_README.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(new_readme)
        click.echo(click.style(f"✅ Improved README saved to: {filename}", fg="green", bold=True))
        return

    click.echo(f"\n🤖 {click.style('Analyzing README with AI...', fg='cyan')}\n")
    
    analysis = analyze_readme(data['readme'])
    
    if analysis is None:
        click.echo(click.style("❌ AI analysis failed. Check your API key.", fg="red"))
        return
    
    score = parse_score(analysis)
    grade, grade_msg = get_grade(score)
    
    if score_only:
        click.echo(f"\n🎯 Score: {colorize_score(score)} | Grade: {click.style(grade, bold=True)} | {grade_msg}\n")
        return

    click.echo(click.style("="*50, fg="cyan"))
    click.echo(click.style(f"📊 README HEALTH REPORT: {data['name']}", fg="cyan", bold=True))
    click.echo(click.style("="*50, fg="cyan"))
    click.echo(f"🎯 Score: {colorize_score(score)}  |  Grade: {click.style(grade, bold=True)}  |  {grade_msg}")
    click.echo(click.style("="*50, fg="cyan"))
    click.echo()
    click.echo(colorize_analysis(analysis))

if __name__ == '__main__':
    main()