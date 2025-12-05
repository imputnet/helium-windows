const core = require('@actions/core');
const io = require('@actions/io');
const exec = require('@actions/exec');
const {DefaultArtifactClient} = require('@actions/artifact');
const glob = require('@actions/glob');
const path = require('path');

async function run() {
    const started_at = Math.floor(new Date() / 1000);

    process.on('SIGINT', function() {
    })
    const from_artifact = core.getBooleanInput('from_artifact', {required: true});
    const gen_installer = core.getBooleanInput('gen_installer', {required: false});
    const do_package = core.getBooleanInput('do_package', {required: false});
    const make_sign_artifact = core.getBooleanInput('make_sign_artifact', {required: false});

    const arm = core.getBooleanInput('arm', {required: false})
    console.log(`artifact: ${from_artifact}, gen_installer: ${gen_installer}, do_package: ${do_package}`);

    const artifact = new DefaultArtifactClient();
    const artifactName = arm ? 'build-artifact-arm64' : 'build-artifact-x86_64';
    const signArtifactName = arm ? 'sign-artifact-arm64' : 'sign-artifact-x86_64';
    const same_runner = gen_installer || do_package;

    if (from_artifact && !same_runner) {
        const artifactInfo = await artifact.getArtifact(artifactName);
        await artifact.downloadArtifact(artifactInfo.artifact.id, {path: 'C:\\helium-windows\\build'});
        await exec.exec('7z', ['x', 'C:\\helium-windows\\build\\artifacts.zip',
            '-oC:\\helium-windows\\build', '-y']);
        await io.rmRF('C:\\helium-windows\\build\\artifacts.zip');
    }

    const args = ['build.py', '--ci', String(started_at), '-j', '2']
    if (arm)
        args.push('--arm')

    if (gen_installer) {
        const patterns = ['*.7z', 'mini_installer.*', '*.ex_'];
        const prefix = 'C:\\helium-windows\\build\\src\\out\\Default';
        const globber = await glob.create(patterns.map(pattern => path.join(prefix, pattern)).join('\n'));

        const binaries = [
            ...await globber.glob(),
            path.join(prefix, 'gen/chrome/installer/mini_installer')
        ];

        await Promise.all(binaries.map(path => io.rmRF(path)));
        args.push('--build-installer');
    } else if (do_package) {
        args.push('--do-package')
    }

    await exec.exec('python', ['-m', 'pip', 'install', 'httplib2==0.22.0', 'Pillow'], {
        cwd: 'C:\\helium-windows',
        ignoreReturnCode: true
    });
    const retCode = await exec.exec('python', args, {
        cwd: 'C:\\helium-windows',
        ignoreReturnCode: true
    });

    if (retCode > 0 && retCode !== 42) {
        throw `Unexpected return code: ${retCode}`
    }

    core.setOutput('finished', retCode === 0);

    if (make_sign_artifact) {
        if (retCode !== 0) throw "build was unsuccessful";

        const patterns = ['chrome*.exe', 'notification_helper.exe', 'setup.exe', 'mini_installer.exe', '*.dll'];

        const prefix = 'C:\\helium-windows\\build\\src\\out\\Default';
        const globber = await glob.create(patterns.map(pattern => path.join(prefix, pattern)).join('\n'));

        const binaries = await globber.glob();
        try { await artifact.deleteArtifact(signArtifactName); } catch {}
        const { id } = await artifact.uploadArtifact(signArtifactName, binaries, prefix, { compressionLevel: 0 });
        core.setOutput('artifact_id', id);
    }

    if (do_package) {
        const globber = await glob.create('C:\\helium-windows\\build\\helium*',
            {matchDirectories: false});
        let packageList = await globber.glob();
        const finalArtifactName = arm ? 'helium-arm64' : 'helium-x86_64';
        for (let i = 0; i < 5; ++i) {
            try {
                await artifact.deleteArtifact(finalArtifactName);
            } catch (e) {
                // ignored
            }
            try {
                await artifact.uploadArtifact(finalArtifactName, packageList,
                    'C:\\helium-windows\\build', { compressionLevel: 0 });
                break;
            } catch (e) {
                console.error(`Upload artifact failed: ${e}`);
                // Wait 10 seconds between the attempts
                await new Promise(r => setTimeout(r, 10000));
            }
        }

        const { exitCode, stdout } = await exec.getExecOutput('python', [
            'helium-chromium\\utils\\helium_version.py',
            '--print',
            '--tree', 'helium-chromium',
            '--platform-tree', '.'
        ]);

        if (exitCode !== 0) throw `failed getting version: ${exitCode}`;
        core.setOutput('version', stdout.trim());
    }

    if (!gen_installer && !make_sign_artifact) {
        await exec.exec('7z', ['a', '-tzip', 'C:\\helium-windows\\artifacts.zip',
            'C:\\helium-windows\\build\\src', '-mx=3', '-mtc=on'], {ignoreReturnCode: true});
        for (let i = 0; i < 5; ++i) {
            try {
                await artifact.deleteArtifact(artifactName);
            } catch (e) {
                // ignored
            }
            try {
                await artifact.uploadArtifact(artifactName, ['C:\\helium-windows\\artifacts.zip'],
                    'C:\\helium-windows', { compressionLevel: 0 });
                break;
            } catch (e) {
                console.error(`Upload artifact failed: ${e}`);
                // Wait 10 seconds between the attempts
                await new Promise(r => setTimeout(r, 10000));
            }
        }
    }
}

run().catch(err => core.setFailed(err.message));
