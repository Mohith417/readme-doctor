import click
import os
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
        elif line.startswith('- '):
            output.append(click.style(line, fg="green"))
        else:
            output.append(line)
    return '\n'.join(output)

@click.command()
@click.argument('repo_urls', nargs=-1, required=True)
@click.option('--generate', is_flag=True, help='Generate an improved README')
@click.option('--score-only', is_flag=True, help='Show only the score')
@click.option('--token', default=None, help='GitHub personal access token for private repos')
def main(repo_urls, generate, score_only, token):
    """README Doctor - Analyze any GitHub repo's README using AI"""

    github_token = token or os.getenv("GITHUB_TOKEN")

    if len(repo_urls) > 1 and not score_only:
        click.echo(click.style(f"\n📊 Analyzing {len(repo_urls)} repos...\n", fg="cyan", bold=True))
        results = []
        for url in repo_urls:
            click.echo(f"🔍 Fetching: {click.style(url, fg='cyan')}")
            data = fetch_repo_data(url, github_token)
            if data is None:
                click.echo(click.style(f"❌ Could not fetch {url}", fg="red"))
                continue
            analysis = analyze_readme(data['readme'])
            score = parse_score(analysis)
            grade, grade_msg = get_grade(score)
            results.append((data['name'], score, grade))
            click.echo(f"✅ {click.style(data['name'], bold=True)} → {colorize_score(score)} | Grade: {click.style(grade, bold=True)}")

        click.echo(click.style("\n" + "="*50, fg="cyan"))
        click.echo(click.style("📊 SUMMARY", fg="cyan", bold=True))
        click.echo(click.style("="*50, fg="cyan"))
        for name, score, grade in sorted(results, key=lambda x: x[1] or 0, reverse=True):
            click.echo(f"  {click.style(name, bold=True)}: {colorize_score(score)} | {grade}")
        return

    repo_url = repo_urls[0]

    click.echo(f"\n🔍 Fetching repo: {click.style(repo_url, fg='cyan')}\n")

    data = fetch_repo_data(repo_url, github_token)

    if data is None:
        click.echo(click.style("❌ Could not fetch repo. Check the URL and try again.", fg="red"))
        return

    click.echo(f"✅ Repo: {click.style(data['name'], fg='cyan', bold=True)}")
    click.echo(f"📝 Description: {data['description']}")
    click.echo(f"⭐ Stars: {click.style(str(data['stars']), fg='yellow')}")
    click.echo(f"💻 Language: {data['language']}")

    if generate:
        click.echo(f"\n✨ {click.style('Generating improved README...', fg='cyan')}\n")

        max_attempts = 3
        best_readme = None
        best_score = 0

        for attempt in range(1, max_attempts + 1):
            click.echo(f"🔄 Attempt {attempt}/{max_attempts}...")

            new_readme = generate_readme(data)
            if new_readme is None:
                click.echo(click.style("❌ README generation failed.", fg="red"))
                return

            analysis = analyze_readme(new_readme)
            score = parse_score(analysis)
            grade, _ = get_grade(score)

            click.echo(f"📊 Generated README score: {colorize_score(score)} | Grade: {click.style(grade, bold=True)}")

            if score is not None and score > best_score:
                best_score = score
                best_readme = new_readme

            if score is not None and score >= 85:
                click.echo(click.style(f"✅ Target score reached!", fg="green", bold=True))
                break

            if attempt < max_attempts:
                click.echo(f"⚡ Score below 85, regenerating with feedback...\n")
                data['previous_feedback'] = analysis

        filename = f"{data['name']}_improved_README.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(best_readme)

        click.echo(click.style(f"\n✅ Best README (score: {best_score}/100) saved to: {filename}", fg="green", bold=True))
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