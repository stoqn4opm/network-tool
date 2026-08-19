class NetworkTool < Formula
  desc "Agent-drivable mitmproxy wrapper for capturing iOS and web API traffic"
  homepage "https://github.com/stoqn4opm/network-tool"
  url "https://github.com/stoqn4opm/network-tool/archive/refs/tags/v0.1.0.tar.gz"
  # Filled in at release time (shasum -a 256 of the tag tarball). Not used by --HEAD.
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"
  head "https://github.com/stoqn4opm/network-tool.git", branch: "main"

  def install
    # Support files are private (not symlinked onto PATH).
    libexec.install "addons/capture.py"
    libexec.install "libexec/flow_read.py", "libexec/common.sh",
                    "libexec/pick_flow.py", "libexec/freshen.py"

    # The launcher. bin.install sets it executable and symlinks it onto PATH.
    bin.install "bin/ntool"

    # Bake the (version-stable) libexec location into the launcher.
    inreplace bin/"ntool", "@@LIBEXEC@@", opt_libexec
  end

  def caveats
    <<~EOS
      network-tool drives mitmproxy, which Homebrew ships as a cask
      (a formula cannot install a cask automatically):

        brew install --cask mitmproxy

      Then trust the CA and start capturing:

        ntool setup
        ntool capture on --sim <AppName>
    EOS
  end

  test do
    assert_match "ntool #{version}", shell_output("#{bin}/ntool version")
    assert_path_exists opt_libexec/"capture.py"
    assert_path_exists opt_libexec/"flow_read.py"
  end
end
