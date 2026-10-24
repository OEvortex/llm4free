import os
import platform
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, TypedDict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:
    from llm4free.swiftcli import CLI, option, argument
except Exception:
    class CLI:
        def __init__(self,*a,**k): pass
        def command(self,*a,**k): return lambda f: f
        def run(self): pass
    option = lambda *a, **k: (lambda f: f)
    argument = lambda *a, **k: (lambda f: f)
from llm4free.zeroart import figlet_format

# Lazy import for huggingface_hub
HfApi = None


def _ensure_huggingface_hub():
    """Ensure huggingface_hub is imported when needed."""
    global HfApi
    if HfApi is None:
        try:
            from huggingface_hub import HfApi as _HfApi

            HfApi = _HfApi
        except ImportError:
            raise ImportError(
                "huggingface_hub is required for GGUF conversion. "
                "Install it with: pip install huggingface_hub"
            )
    return HfApi


console = Console()


class ConversionError(Exception):
    """Custom exception for when things don't go as planned! ⚠️"""

    pass


class QuantizationMethod(TypedDict):
    """Type definition for quantization method descriptions."""

    description: str


class ModelConverter:
    """Handles the conversion of Hugging Face models to GGUF format."""

    VALID_METHODS: Dict[str, str] = {
        # Full precision types
        "f32": "32-bit floating point - full precision, largest size",
        "fp16": "16-bit floating point - maximum accuracy, large size",
        "f16": "16-bit floating point - alias for fp16",
        "bf16": "bfloat16 - good balance for training and some models",
        "auto": "Auto-detect best 16-bit type based on model tensors",
        # K-Quant types (super-block quantization)
        "q2_k": "2-bit K-quant (smallest size, lowest accuracy)",
        "q2_k_s": "2-bit K-quant small - maximum compression",
        "q3_k_l": "3-bit K-quant large - balanced for size/accuracy",
        "q3_k_m": "3-bit K-quant medium - good balance for most use cases",
        "q3_k_s": "3-bit K-quant small - optimized for speed",
        "q4_0": "4-bit quantization (legacy) - standard 4-bit, auto-repacks for ARM",
        "q4_1": "4-bit quantization (legacy) - improved accuracy over q4_0",
        "q4_k_l": "4-bit K-quant large - highest quality 4-bit",
        "q4_k_m": "4-bit K-quant medium - balanced for most models",
        "q4_k_s": "4-bit K-quant small - optimized for speed",
        "q5_0": "5-bit quantization (legacy) - high accuracy",
        "q5_1": "5-bit quantization (legacy) - improved accuracy over q5_0",
        "q5_k_l": "5-bit K-quant large - highest quality 5-bit",
        "q5_k_m": "5-bit K-quant medium - best balance for quality/size",
        "q5_k_s": "5-bit K-quant small - optimized for speed",
        "q6_k": "6-bit K-quant - near-lossless quality",
        "q8_0": "8-bit quantization - near-original quality",
        # Ternary quantization (experimental)
        "tq1_0": "1-bit ternary quantization - experimental, extreme compression",
        "tq2_0": "2-bit ternary quantization - experimental, very small size",
    }

    VALID_IMATRIX_METHODS: Dict[str, str] = {
        # 1-bit IQ types (extreme compression, requires imatrix)
        "iq1_s": "1-bit IQ small - extreme compression, requires imatrix",
        "iq1_m": "1-bit IQ medium - extreme compression, requires imatrix",
        # 2-bit IQ types
        "iq2_xxs": "2-bit IQ extra extra small - maximum compression",
        "iq2_xs": "2-bit IQ extra small - very high compression",
        "iq2_s": "2-bit IQ small - high compression",
        "iq2_m": "2-bit IQ medium - balanced compression",
        # 3-bit IQ types
        "iq3_xxs": "3-bit IQ extra extra small - maximum compression",
        "iq3_xs": "3-bit IQ extra small - high compression",
        "iq3_s": "3-bit IQ small - balanced compression",
        "iq3_m": "3-bit IQ medium - balanced importance-based",
        # 4-bit IQ types
        "iq4_nl": "4-bit IQ non-linear - best accuracy for 4-bit",
        "iq4_xs": "4-bit IQ extra small - maximum 4-bit compression",
        # K-Quant types that benefit from imatrix
        "q2_k": "2-bit K-quant with imatrix - improved quality",
        "q2_k_s": "2-bit K-quant small with imatrix",
        "q3_k_s": "3-bit K-quant small with imatrix",
        "q3_k_m": "3-bit K-quant medium with imatrix",
        "q3_k_l": "3-bit K-quant large with imatrix",
        "q4_k_s": "4-bit K-quant small with imatrix",
        "q4_k_m": "4-bit K-quant medium with imatrix",
        "q5_k_s": "5-bit K-quant small with imatrix",
        "q5_k_m": "5-bit K-quant medium with imatrix",
        "q6_k": "6-bit K-quant with imatrix",
    }
    # Default output type options (matches llama.cpp)
    VALID_OUTTYPES: Set[str] = {"f32", "f16", "bf16", "q8_0", "tq1_0", "tq2_0", "auto"}

    def __init__(
        self,
        model_id: str,
        username: Optional[str] = None,
        token: Optional[str] = None,
        quantization_methods: str = "q4_k_m",
        use_imatrix: bool = False,
        train_data_file: Optional[str] = None,
        split_model: bool = False,
        split_max_tensors: int = 256,
        split_max_size: Optional[str] = None,
        # New llama.cpp options
        outtype: str = "f16",
        vocab_only: bool = False,
        remote: bool = False,
        dry_run: bool = False,
        no_lazy: bool = False,
        model_name: Optional[str] = None,
        small_first_shard: bool = False,
    ) -> None:
        self.model_id = model_id
        self.username = username
        self.token = token
        self.quantization_methods = quantization_methods.split(",")
        self.model_name = model_name or model_id.split("/")[-1]
        self.workspace = Path(os.getcwd())
        self.use_imatrix = use_imatrix
        self.train_data_file = train_data_file
        self.use_split = split_model
        self.split_max_tensors = split_max_tensors
        self.split_max_size = split_max_size
        # New llama.cpp options
        self.outtype = outtype.lower()
        self.vocab_only = vocab_only
        self.remote = remote
        self.dry_run = dry_run
        self.no_lazy = no_lazy
        self.small_first_shard = small_first_shard
        # Determine if we only need the base conversion (no quantization)
        self.base_only = (
            self.outtype in self.VALID_OUTTYPES
            and len(self.quantization_methods) == 1
            and self.quantization_methods[0] in ["fp16", "f16", "f32", "bf16", "auto"]
        )

    def validate_inputs(self) -> None:
        """Validates all input parameters."""
        if "/" not in self.model_id:
            raise ValueError("Invalid model ID format. Expected format: 'organization/model-name'")

        if self.use_imatrix:
            invalid_methods = [
                m for m in self.quantization_methods if m not in self.VALID_IMATRIX_METHODS
            ]
            if invalid_methods:
                raise ValueError(
                    f"Invalid imatrix quantization methods: {', '.join(invalid_methods)}.\n"
                    f"Valid methods are: {', '.join(self.VALID_IMATRIX_METHODS.keys())}"
                )
            if not self.train_data_file and not os.path.exists("llama.cpp/groups_merged.txt"):
                raise ValueError("Training data file is required for imatrix quantization")
        else:
            invalid_methods = [m for m in self.quantization_methods if m not in self.VALID_METHODS]
            if invalid_methods:
                raise ValueError(
                    f"Invalid quantization methods: {', '.join(invalid_methods)}.\n"
                    f"Valid methods are: {', '.join(self.VALID_METHODS.keys())}"
                )

        if bool(self.username) != bool(self.token):
            raise ValueError("Both username and token must be provided for upload, or neither.")

        # Validate outtype
        if self.outtype not in self.VALID_OUTTYPES:
            raise ValueError(
                f"Invalid output type: {self.outtype}.\n"
                f"Valid types are: {', '.join(self.VALID_OUTTYPES)}"
            )

        if self.use_split and self.split_max_size:
            try:
                # Support K, M, G units (like llama.cpp's split_str_to_n_bytes)
                if self.split_max_size[-1].upper() in ["K", "M", "G"]:
                    int(self.split_max_size[:-1])
                    unit = self.split_max_size[-1].upper()
                    if unit not in ["K", "M", "G"]:
                        raise ValueError("Split max size must end with K, M, or G")
                elif self.split_max_size.isnumeric():
                    int(self.split_max_size)
                else:
                    raise ValueError("Invalid format")
            except (ValueError, IndexError):
                raise ValueError(
                    "Invalid split max size format. Use format like '256M', '5G', or numeric bytes"
                )

    @staticmethod
    def check_dependencies() -> Dict[str, bool]:
        """Check if all required dependencies are installed with cross-platform support."""
        system = platform.system()

        dependencies: Dict[str, str] = {
            "git": "Git version control",
            "cmake": "CMake build system",
            "ninja": "Ninja build system (optional)",
        }

        # Add platform-specific dependencies
        if system != "Windows":
            dependencies["pip3"] = "Python package installer"
        else:
            dependencies["pip"] = "Python package installer"

        status: Dict[str, bool] = {}

        for cmd, desc in dependencies.items():
            try:
                if system == "Windows":
                    # Use 'where' command on Windows
                    result = subprocess.run(["where", cmd], capture_output=True, text=True)
                    status[cmd] = result.returncode == 0
                else:
                    # Use 'which' command on Unix-like systems
                    result = subprocess.run(["which", cmd], capture_output=True, text=True)
                    status[cmd] = result.returncode == 0
            except (FileNotFoundError, subprocess.SubprocessError):
                status[cmd] = False

        # Special check for Python - try different variants
        python_variants = (
            ["python3", "python", "py"] if system != "Windows" else ["python", "py", "python3"]
        )
        status["python"] = False
        for variant in python_variants:
            try:
                if system == "Windows":
                    result = subprocess.run(["where", variant], capture_output=True)
                else:
                    result = subprocess.run(["which", variant], capture_output=True)
                if result.returncode == 0:
                    status["python"] = True
                    break
            except Exception:
                continue

        # Check for C++ compiler
        cpp_compilers = ["cl", "g++", "clang++"] if system == "Windows" else ["g++", "clang++"]
        status["cpp_compiler"] = False
        for compiler in cpp_compilers:
            try:
                if system == "Windows":
                    result = subprocess.run(["where", compiler], capture_output=True)
                else:
                    result = subprocess.run(["which", compiler], capture_output=True)
                if result.returncode == 0:
                    status["cpp_compiler"] = True
                    break
            except Exception:
                continue

        dependencies["python"] = "Python interpreter"
        dependencies["cpp_compiler"] = "C++ compiler (g++, clang++, or MSVC)"

        return status

    def detect_hardware(self) -> Dict[str, bool]:
        """Detect available hardware acceleration with improved cross-platform support."""
        hardware: Dict[str, bool] = {
            "cuda": False,
            "metal": False,
            "opencl": False,
            "vulkan": False,
            "rocm": False,
            "blas": False,
            "accelerate": False,
        }

        system = platform.system()

        # Check CUDA
        try:
            # Check for nvcc compiler
            if (
                subprocess.run(
                    ["nvcc", "--version"], capture_output=True, shell=(system == "Windows")
                ).returncode
                == 0
            ):
                hardware["cuda"] = True
            # Also check for nvidia-smi as fallback
            elif (
                subprocess.run(
                    ["nvidia-smi"], capture_output=True, shell=(system == "Windows")
                ).returncode
                == 0
            ):
                hardware["cuda"] = True
        except (FileNotFoundError, subprocess.SubprocessError):
            # Check for CUDA libraries on Windows
            if system == "Windows":
                cuda_paths = [
                    os.environ.get("CUDA_PATH"),
                    "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA",
                    "C:\\Program Files (x86)\\NVIDIA GPU Computing Toolkit\\CUDA",
                ]
                for cuda_path in cuda_paths:
                    if cuda_path and os.path.exists(cuda_path):
                        hardware["cuda"] = True
                        break

        # Check Metal (macOS)
        if system == "Darwin":
            try:
                # Check for Xcode command line tools
                if (
                    subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True).returncode
                    == 0
                ):
                    hardware["metal"] = True
                # Check for Metal framework
                if os.path.exists("/System/Library/Frameworks/Metal.framework"):
                    hardware["metal"] = True
                # macOS also supports Accelerate framework
                if os.path.exists("/System/Library/Frameworks/Accelerate.framework"):
                    hardware["accelerate"] = True
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

        # Check OpenCL
        try:
            if system == "Windows":
                # Check for OpenCL on Windows
                opencl_paths = [
                    "C:\\Windows\\System32\\OpenCL.dll",
                    "C:\\Windows\\SysWOW64\\OpenCL.dll",
                ]
                if any(os.path.exists(path) for path in opencl_paths):
                    hardware["opencl"] = True
            else:
                if subprocess.run(["clinfo"], capture_output=True).returncode == 0:
                    hardware["opencl"] = True
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        # Check Vulkan
        try:
            if system == "Windows":
                # Check for Vulkan on Windows
                vulkan_paths = [
                    "C:\\Windows\\System32\\vulkan-1.dll",
                    "C:\\Windows\\SysWOW64\\vulkan-1.dll",
                ]
                if any(os.path.exists(path) for path in vulkan_paths):
                    hardware["vulkan"] = True
            else:
                if subprocess.run(["vulkaninfo"], capture_output=True).returncode == 0:
                    hardware["vulkan"] = True
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        # Check ROCm (AMD)
        try:
            if (
                subprocess.run(
                    ["rocm-smi"], capture_output=True, shell=(system == "Windows")
                ).returncode
                == 0
            ):
                hardware["rocm"] = True
            elif system == "Linux":
                # Check for ROCm installation
                rocm_paths = ["/opt/rocm", "/usr/lib/x86_64-linux-gnu/librocm-smi64.so"]
                if any(os.path.exists(path) for path in rocm_paths):
                    hardware["rocm"] = True
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        # Check for BLAS libraries
        try:
            import numpy as np  # type: ignore[import-untyped]

            # Check if numpy is linked with optimized BLAS
            config = np.__config__.show()
            if any(lib in str(config).lower() for lib in ["openblas", "mkl", "atlas", "blis"]):
                hardware["blas"] = True
        except (ImportError, AttributeError):
            # Fallback: check for common BLAS libraries
            if system == "Linux":
                blas_libs = [
                    "/usr/lib/x86_64-linux-gnu/libopenblas.so",
                    "/usr/lib/x86_64-linux-gnu/libblas.so",
                ]
                if any(os.path.exists(lib) for lib in blas_libs):
                    hardware["blas"] = True
            elif system == "Windows":
                # Check for Intel MKL or OpenBLAS on Windows
                mkl_paths = ["C:\\Program Files (x86)\\Intel\\oneAPI\\mkl"]
                if any(os.path.exists(path) for path in mkl_paths):
                    hardware["blas"] = True

        return hardware

    def setup_llama_cpp(self) -> None:
        """Sets up and builds llama.cpp repository with robust error handling."""
        llama_path = self.workspace / "llama.cpp"
        system = platform.system()

        with console.status("[bold green]Setting up llama.cpp...") as status:
            # Clone llama.cpp if not exists
            if not llama_path.exists():
                try:
                    subprocess.run(
                        ["git", "clone", "https://github.com/ggerganov/llama.cpp"], check=True
                    )
                except subprocess.CalledProcessError as e:
                    raise ConversionError(f"Failed to clone llama.cpp repository: {e}")

            original_cwd = os.getcwd()
            try:
                os.chdir(llama_path)

                # Update to latest version
                try:
                    subprocess.run(["git", "pull"], capture_output=True, check=False)
                except subprocess.CalledProcessError:
                    console.print("[yellow]Warning: Could not update llama.cpp repository")

                # Clean any existing build directory to avoid cached CMake variables
                build_dir = Path("build")
                if build_dir.exists():
                    console.print(
                        "[yellow]Cleaning existing build directory to avoid CMake cache conflicts..."
                    )
                    import shutil

                    try:
                        shutil.rmtree(build_dir)
                        console.print("[green]Build directory cleaned successfully")
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not clean build directory: {e}")

                # Check if we're in a Nix environment
                is_nix = system == "Linux" and os.path.exists("/nix/store")

                if is_nix:
                    console.print(
                        "[yellow]Detected Nix environment. Using system Python packages..."
                    )
                    # In Nix, we need to use the system Python packages
                    try:
                        # Try to import required packages to check if they're available
                        import numpy  # type: ignore[import-untyped]
                        import sentencepiece  # type: ignore
                        import torch  # type: ignore
                        import transformers  # type: ignore

                        console.print("[green]Required Python packages are already installed.")
                    except ImportError:
                        console.print("[red]Missing required Python packages in Nix environment.")
                        console.print("[yellow]Please install them using:")
                        console.print(
                            "nix-shell -p python3Packages.torch python3Packages.numpy python3Packages.sentencepiece python3Packages.transformers"
                        )
                        raise ConversionError("Missing required Python packages in Nix environment")
                else:
                    # In non-Nix environments, install requirements if they exist
                    if os.path.exists("requirements.txt"):
                        try:
                            pip_cmd = "pip" if system == "Windows" else "pip3"
                            subprocess.run(
                                [pip_cmd, "install", "-r", "requirements.txt"], check=True
                            )
                        except subprocess.CalledProcessError as e:
                            if "externally-managed-environment" in str(e):
                                console.print(
                                    "[yellow]Detected externally managed Python environment."
                                )
                                console.print(
                                    "[yellow]Please install the required packages manually:"
                                )
                                console.print("pip install torch numpy sentencepiece transformers")
                                raise ConversionError(
                                    "Failed to install requirements in externally managed environment"
                                )
                            else:
                                console.print(
                                    f"[yellow]Warning: Failed to install requirements: {e}"
                                )

                # Detect available hardware
                hardware = self.detect_hardware()
                console.print("[bold green]Detected hardware acceleration:")
                for hw, available in hardware.items():
                    console.print(f"  {'✓' if available else '✗'} {hw.upper()}")

                # Clear any environment variables that might cause conflicts
                env_vars_to_clear = [
                    "LLAMA_CUBLAS",
                    "LLAMA_CLBLAST",
                    "LLAMA_HIPBLAS",
                    "LLAMA_METAL",
                    "LLAMA_ACCELERATE",
                    "LLAMA_OPENBLAS",
                ]
                for var in env_vars_to_clear:
                    if var in os.environ:
                        console.print(f"[yellow]Clearing conflicting environment variable: {var}")
                        del os.environ[var]

                # Configure CMake build with robust options
                cmake_args: List[str] = ["cmake", "-B", "build"]

                # Add basic CMake options
                cmake_args.extend(
                    [
                        "-DCMAKE_BUILD_TYPE=Release",
                        "-DLLAMA_BUILD_TESTS=OFF",
                        "-DLLAMA_BUILD_EXAMPLES=ON",
                        "-DLLAMA_BUILD_SERVER=OFF",
                        # Disable optional dependencies that might cause issues
                        "-DLLAMA_CURL=OFF",  # Disable CURL (not needed for GGUF conversion)
                        "-DLLAMA_LLGUIDANCE=OFF",  # Disable LLGuidance (optional feature)
                    ]
                )

                # Add hardware acceleration options with latest 2025 llama.cpp GGML flags
                # Use priority order: CUDA > Metal > Vulkan > OpenCL > ROCm > BLAS > Accelerate
                acceleration_enabled = False

                if hardware["cuda"]:
                    # Latest 2025 GGML CUDA flags (LLAMA_CUBLAS is deprecated)
                    cmake_args.extend(["-DGGML_CUDA=ON"])
                    console.print("[green]Enabling CUDA acceleration (GGML_CUDA=ON)")
                    acceleration_enabled = True
                elif hardware["metal"]:
                    # Latest 2025 GGML Metal flags for macOS
                    cmake_args.extend(["-DGGML_METAL=ON"])
                    console.print("[green]Enabling Metal acceleration (GGML_METAL=ON)")
                    acceleration_enabled = True
                elif hardware["vulkan"]:
                    # Latest 2025 GGML Vulkan flags
                    cmake_args.extend(["-DGGML_VULKAN=ON"])
                    console.print("[green]Enabling Vulkan acceleration (GGML_VULKAN=ON)")
                    acceleration_enabled = True
                elif hardware["opencl"]:
                    # Latest 2025 GGML OpenCL flags (LLAMA_CLBLAST is deprecated)
                    cmake_args.extend(["-DGGML_OPENCL=ON"])
                    console.print("[green]Enabling OpenCL acceleration (GGML_OPENCL=ON)")
                    acceleration_enabled = True
                elif hardware["rocm"]:
                    # Latest 2025 GGML ROCm/HIP flags
                    cmake_args.extend(["-DGGML_HIPBLAS=ON"])
                    console.print("[green]Enabling ROCm acceleration (GGML_HIPBLAS=ON)")
                    acceleration_enabled = True
                elif hardware["blas"]:
                    # Latest 2025 GGML BLAS flags with vendor detection
                    cmake_args.extend(["-DGGML_BLAS=ON"])
                    # Try to detect BLAS vendor for optimal performance
                    if system == "Darwin":
                        cmake_args.extend(["-DGGML_BLAS_VENDOR=Accelerate"])
                    elif "mkl" in str(hardware).lower():
                        cmake_args.extend(["-DGGML_BLAS_VENDOR=Intel10_64lp"])
                    else:
                        cmake_args.extend(["-DGGML_BLAS_VENDOR=OpenBLAS"])
                    console.print("[green]Enabling BLAS acceleration (GGML_BLAS=ON)")
                    acceleration_enabled = True
                elif hardware["accelerate"]:
                    # Latest 2025 GGML Accelerate framework flags for macOS
                    cmake_args.extend(["-DGGML_ACCELERATE=ON"])
                    console.print("[green]Enabling Accelerate framework (GGML_ACCELERATE=ON)")
                    acceleration_enabled = True

                if not acceleration_enabled:
                    console.print("[yellow]No hardware acceleration available, using CPU only")

                # Platform-specific optimizations
                if system == "Windows":
                    # Use Visual Studio generator on Windows if available
                    try:
                        vs_result = subprocess.run(["where", "msbuild"], capture_output=True)
                        if vs_result.returncode == 0:
                            cmake_args.extend(["-G", "Visual Studio 17 2022"])
                        else:
                            cmake_args.extend(["-G", "MinGW Makefiles"])
                    except Exception:
                        cmake_args.extend(["-G", "MinGW Makefiles"])
                else:
                    # Use Ninja if available on Unix systems
                    try:
                        ninja_cmd = "ninja" if system != "Windows" else "ninja.exe"
                        if (
                            subprocess.run(["which", ninja_cmd], capture_output=True).returncode
                            == 0
                        ):
                            cmake_args.extend(["-G", "Ninja"])
                    except Exception:
                        pass  # Fall back to default generator

                # Configure the build with error handling and multiple fallback strategies
                status.update("[bold green]Configuring CMake build...")
                config_success = False

                # Try main configuration
                try:
                    console.print(f"[cyan]CMake command: {' '.join(cmake_args)}")
                    result = subprocess.run(cmake_args, capture_output=True, text=True)
                    if result.returncode == 0:
                        config_success = True
                        console.print("[green]CMake configuration successful!")
                    else:
                        console.print(f"[red]CMake configuration failed: {result.stderr}")
                except subprocess.CalledProcessError as e:
                    console.print(f"[red]CMake execution failed: {e}")

                # Try fallback without hardware acceleration if main config failed
                if not config_success:
                    console.print(
                        "[yellow]Attempting fallback configuration without hardware acceleration..."
                    )
                    console.print("[cyan]Using CPU-only build configuration...")
                    fallback_args = [
                        "cmake",
                        "-B",
                        "build",
                        "-DCMAKE_BUILD_TYPE=Release",
                        "-DLLAMA_BUILD_TESTS=OFF",
                        "-DLLAMA_BUILD_EXAMPLES=ON",
                        "-DLLAMA_BUILD_SERVER=OFF",
                        # Disable optional dependencies that might cause issues
                        "-DLLAMA_CURL=OFF",  # Disable CURL (not needed for GGUF conversion)
                        "-DLLAMA_LLGUIDANCE=OFF",  # Disable LLGuidance (optional feature)
                        # Enable CPU optimizations
                        "-DGGML_NATIVE=OFF",  # Disable native optimizations for compatibility
                        "-DGGML_AVX=ON",  # Enable AVX if available
                        "-DGGML_AVX2=ON",  # Enable AVX2 if available
                        "-DGGML_FMA=ON",  # Enable FMA if available
                    ]
                    try:
                        console.print(f"[cyan]Fallback CMake command: {' '.join(fallback_args)}")
                        result = subprocess.run(fallback_args, capture_output=True, text=True)
                        if result.returncode == 0:
                            config_success = True
                            console.print("[green]Fallback CMake configuration successful!")
                        else:
                            console.print(
                                f"[red]Fallback CMake configuration failed: {result.stderr}"
                            )
                    except subprocess.CalledProcessError as e:
                        console.print(f"[red]Fallback CMake execution failed: {e}")

                # Try minimal configuration as last resort
                if not config_success:
                    console.print("[yellow]Attempting minimal configuration...")
                    minimal_args = [
                        "cmake",
                        "-B",
                        "build",
                        "-DCMAKE_BUILD_TYPE=Release",
                        # Disable optional dependencies that might cause issues
                        "-DLLAMA_CURL=OFF",  # Disable CURL (not needed for GGUF conversion)
                        "-DLLAMA_LLGUIDANCE=OFF",  # Disable LLGuidance (optional feature)
                        "-DLLAMA_BUILD_SERVER=OFF",  # Disable server (not needed for conversion)
                        "-DLLAMA_BUILD_TESTS=OFF",  # Disable tests (not needed for conversion)
                    ]
                    try:
                        console.print(f"[cyan]Minimal CMake command: {' '.join(minimal_args)}")
                        result = subprocess.run(minimal_args, capture_output=True, text=True)
                        if result.returncode == 0:
                            config_success = True
                            console.print("[green]Minimal CMake configuration successful!")
                        else:
                            console.print(
                                f"[red]Minimal CMake configuration failed: {result.stderr}"
                            )
                            raise ConversionError(
                                f"All CMake configuration attempts failed. Last error: {result.stderr}"
                            )
                    except subprocess.CalledProcessError as e:
                        raise ConversionError(f"All CMake configuration attempts failed: {e}")

                if not config_success:
                    raise ConversionError(
                        "CMake configuration failed with all attempted strategies"
                    )

                # Build the project
                status.update("[bold green]Building llama.cpp...")
                build_cmd = ["cmake", "--build", "build", "--config", "Release"]

                # Add parallel build option
                cpu_count = os.cpu_count() or 1
                if system == "Windows":
                    build_cmd.extend(["--parallel", str(cpu_count)])
                else:
                    build_cmd.extend(["-j", str(cpu_count)])

                try:
                    result = subprocess.run(build_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        console.print(f"[red]Build failed: {result.stderr}")
                        # Try single-threaded build as fallback
                        console.print("[yellow]Attempting single-threaded build...")
                        fallback_build = ["cmake", "--build", "build", "--config", "Release"]
                        result = subprocess.run(fallback_build, capture_output=True, text=True)
                        if result.returncode != 0:
                            raise ConversionError(f"Build failed: {result.stderr}")
                except subprocess.CalledProcessError as e:
                    raise ConversionError(f"Build failed: {e}")

                console.print("[green]llama.cpp built successfully!")

            finally:
                os.chdir(original_cwd)

    def display_config(self) -> None:
        """Displays the current configuration in a formatted table."""
        table = Table(title="Configuration", show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Model ID", self.model_id)
        table.add_row("Model Name", self.model_name)
        table.add_row("Username", self.username or "Not provided")
        table.add_row("Token", "****" if self.token else "Not provided")
        table.add_row(
            "Quantization Methods",
            "\n".join(
                f"{method} ({self.VALID_METHODS[method]})" for method in self.quantization_methods
            ),
        )

        console.print(Panel(table))

    def get_binary_path(self, binary_name: str) -> str:
        """Get the correct path to llama.cpp binaries based on platform."""
        system = platform.system()

        # Possible binary locations
        possible_paths = [
            f"./llama.cpp/build/bin/{binary_name}",  # Standard build location
            f"./llama.cpp/build/{binary_name}",  # Alternative build location
            f"./llama.cpp/{binary_name}",  # Root directory
            f"./llama.cpp/build/Release/{binary_name}",  # Windows Release build
            f"./llama.cpp/build/Debug/{binary_name}",  # Windows Debug build
        ]

        # Add .exe extension on Windows
        if system == "Windows":
            possible_paths = [path + ".exe" for path in possible_paths]

        # Find the first existing binary
        for path in possible_paths:
            if os.path.isfile(path):
                return path

        # If not found, return the most likely path and let it fail with a clear error
        default_path = f"./llama.cpp/build/bin/{binary_name}"
        if system == "Windows":
            default_path += ".exe"
        return default_path

    def generate_importance_matrix(
        self, model_path: str, train_data_path: str, output_path: str
    ) -> None:
        """Generates importance matrix for quantization with improved error handling."""
        imatrix_binary = self.get_binary_path("llama-imatrix")

        imatrix_command: List[str] = [
            imatrix_binary,
            "-m",
            model_path,
            "-f",
            train_data_path,
            "-ngl",
            "99",
            "--output-frequency",
            "10",
            "-o",
            output_path,
        ]

        if not os.path.isfile(model_path):
            raise ConversionError(f"Model file not found: {model_path}")

        if not os.path.isfile(train_data_path):
            raise ConversionError(f"Training data file not found: {train_data_path}")

        if not os.path.isfile(imatrix_binary):
            raise ConversionError(f"llama-imatrix binary not found at: {imatrix_binary}")

        console.print("[bold green]Generating importance matrix...")
        console.print(f"[cyan]Command: {' '.join(imatrix_command)}")

        try:
            process = subprocess.Popen(
                imatrix_command,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                if process.returncode != 0:
                    raise ConversionError(f"Failed to generate importance matrix: {stderr}")
            except subprocess.TimeoutExpired:
                console.print("[yellow]Imatrix computation timed out. Sending SIGINT...")
                process.send_signal(signal.SIGINT)
                try:
                    stdout, stderr = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    console.print("[red]Imatrix process still running. Force terminating...")
                    process.kill()
                    stdout, stderr = process.communicate()
                raise ConversionError(f"Imatrix generation timed out: {stderr}")
        except FileNotFoundError:
            raise ConversionError(f"Could not execute llama-imatrix binary: {imatrix_binary}")

        console.print("[green]Importance matrix generation completed.")

    def split_model(self, model_path: str, outdir: str) -> List[str]:
        """Splits the model into smaller chunks with improved error handling."""
        split_binary = self.get_binary_path("llama-gguf-split")

        split_cmd: List[str] = [
            split_binary,
            "--split",
        ]

        if self.split_max_size:
            split_cmd.extend(["--split-max-size", self.split_max_size])
        else:
            split_cmd.extend(["--split-max-tensors", str(self.split_max_tensors)])

        model_path_prefix = ".".join(model_path.split(".")[:-1])
        split_cmd.extend([model_path, model_path_prefix])

        if not os.path.isfile(model_path):
            raise ConversionError(f"Model file not found: {model_path}")

        if not os.path.isfile(split_binary):
            raise ConversionError(f"llama-gguf-split binary not found at: {split_binary}")

        console.print(f"[bold green]Splitting model with command: {' '.join(split_cmd)}")

        try:
            result = subprocess.run(split_cmd, shell=False, capture_output=True, text=True)

            if result.returncode != 0:
                raise ConversionError(f"Error splitting model: {result.stderr}")
        except FileNotFoundError:
            raise ConversionError(f"Could not execute llama-gguf-split binary: {split_binary}")

        console.print("[green]Model split successfully!")

        # Get list of split files
        model_file_prefix = os.path.basename(model_path_prefix)
        try:
            split_files = [
                f
                for f in os.listdir(outdir)
                if f.startswith(model_file_prefix) and f.endswith(".gguf")
            ]
        except OSError as e:
            raise ConversionError(f"Error reading output directory: {e}")

        if not split_files:
            raise ConversionError(
                f"No split files found in {outdir} with prefix {model_file_prefix}"
            )

        console.print(f"[green]Found {len(split_files)} split files: {', '.join(split_files)}")
        return split_files

    def upload_split_files(self, split_files: List[str], outdir: str, repo_id: str) -> None:
        """Uploads split model files to Hugging Face."""
        api = _ensure_huggingface_hub()(token=self.token)

        for file in split_files:
            file_path = os.path.join(outdir, file)
            console.print(f"[bold green]Uploading file: {file}")
            try:
                api.upload_file(
                    path_or_fileobj=file_path,
                    path_in_repo=file,
                    repo_id=repo_id,
                )
                console.print(f"[green]✓ Successfully uploaded: {file}")
            except Exception as e:
                console.print(f"[red]✗ Failed to upload {file}: {e}")
                raise ConversionError(f"Error uploading file {file}: {e}")

    def generate_readme(self, quantized_files: List[str]) -> str:
        """Generate a README.md file for the Hugging Face Hub."""
        readme = f"""# {self.model_name} GGUF

This repository contains GGUF quantized versions of [{self.model_id}](https://huggingface.co/{self.model_id}).

## About

This model was converted using [LLM4Free](https://github.com/LLM4Free/llm4free).

## Quantization Methods

The following quantization methods were used:

"""
        # Add quantization method descriptions
        for method in self.quantization_methods:
            if self.use_imatrix:
                readme += f"- `{method}`: {self.VALID_IMATRIX_METHODS[method]}\n"
            else:
                readme += f"- `{method}`: {self.VALID_METHODS[method]}\n"

        readme += """
## Available Files

The following quantized files are available:

"""
        # Add file information
        for file in quantized_files:
            readme += f"- `{file}`\n"

        if self.use_imatrix:
            readme += """
## Importance Matrix

This model was quantized using importance matrix quantization. The `imatrix.dat` file contains the importance matrix used for quantization.

"""

        readme += """
## Usage

These GGUF files can be used with [llama.cpp](https://github.com/ggerganov/llama.cpp) and compatible tools.

Example usage:
```bash
./main -m model.gguf -n 1024 --repeat_penalty 1.0 --color -i -r "User:" -f prompts/chat-with-bob.txt
```

## Conversion Process

This model was converted using the following command:
```bash
python -m llm4free.Extra.gguf convert \\
    -m "{self.model_id}" \\
    -q "{','.join(self.quantization_methods)}" \\
    {f'-i' if self.use_imatrix else ''} \\
    {f'--train-data "{self.train_data_file}"' if self.train_data_file else ''} \\
    {f'-s' if self.use_split else ''} \\
    {f'--split-max-tensors {self.split_max_tensors}' if self.use_split else ''} \\
    {f'--split-max-size {self.split_max_size}' if self.split_max_size else ''}
```

## License

This repository is licensed under the same terms as the original model.
"""
        return readme

    def create_repository(self, repo_id: str) -> None:
        """Create a new repository on Hugging Face Hub if it doesn't exist."""
        api = _ensure_huggingface_hub()(token=self.token)
        try:
            # Check if repository already exists
            try:
                api.repo_info(repo_id=repo_id)
                console.print(f"[green]✓ Repository {repo_id} already exists")
                return
            except Exception:
                # Repository doesn't exist, create it
                pass

            console.print(f"[bold green]Creating new repository: {repo_id}")
            api.create_repo(repo_id=repo_id, exist_ok=True, private=False, repo_type="model")
            console.print(f"[green]✓ Successfully created repository: {repo_id}")
            console.print(f"[cyan]Repository URL: https://huggingface.co/{repo_id}")
        except Exception as e:
            console.print(f"[red]✗ Failed to create repository: {e}")
            raise ConversionError(f"Error creating repository {repo_id}: {e}")

    def upload_readme(self, readme_content: str, repo_id: str) -> None:
        """Upload README.md to Hugging Face Hub."""
        api = _ensure_huggingface_hub()(token=self.token)
        console.print("[bold green]Uploading README.md with model documentation")
        try:
            api.upload_file(
                path_or_fileobj=readme_content.encode(),
                path_in_repo="README.md",
                repo_id=repo_id,
            )
            console.print("[green]✓ Successfully uploaded: README.md")
        except Exception as e:
            console.print(f"[red]✗ Failed to upload README.md: {e}")
            raise ConversionError(f"Error uploading README.md: {e}")

    def convert(self) -> None:
        """Performs the model conversion process."""
        try:
            # Display banner and configuration
            console.print(f"[bold green]{figlet_format('GGUF Converter')}")
            self.display_config()

            # Validate inputs
            self.validate_inputs()

            # Check dependencies
            deps = self.check_dependencies()
            missing = [
                name for name, installed in deps.items() if not installed and name != "ninja"
            ]
            if missing:
                raise ConversionError(f"Missing required dependencies: {', '.join(missing)}")

            # Setup llama.cpp
            self.setup_llama_cpp()

            # Determine if we need temporary directories (only for uploads)
            needs_temp = bool(self.username and self.token)

            if needs_temp:
                # Use temporary directories for upload case
                with tempfile.TemporaryDirectory() as outdir:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        self._convert_with_dirs(tmpdir, outdir)
            else:
                # Use current directory for local output
                outdir = os.getcwd()
                tmpdir = os.path.join(outdir, "temp_download")
                os.makedirs(tmpdir, exist_ok=True)
                try:
                    self._convert_with_dirs(tmpdir, outdir)
                finally:
                    # Clean up temporary download directory
                    import shutil

                    shutil.rmtree(tmpdir, ignore_errors=True)

            # Display success message
            console.print(
                Panel.fit(
                    "[bold green]✓[/] Conversion completed successfully!\n\n"
                    f"[cyan]Output files can be found in: {self.workspace / self.model_name}[/]",
                    title="Success",
                    border_style="green",
                )
            )

        except Exception as e:
            console.print(Panel.fit(f"[bold red]✗[/] {str(e)}", title="Error", border_style="red"))
            raise

    def _convert_with_dirs(self, tmpdir: str, outdir: str) -> None:
        """Helper method to perform conversion with given directories."""
        # Use outtype for base filename (e.g., model.f16.gguf, model.bf16.gguf)
        outtype_suffix = self.outtype if self.outtype != "auto" else "f16"
        base_gguf = str(Path(outdir) / f"{self.model_name}.{outtype_suffix}.gguf")

        # Download model (or use remote mode)
        local_dir = Path(tmpdir) / self.model_name
        if self.remote:
            console.print(
                "[bold green]Using remote mode - downloading only config and tokenizer..."
            )
            api = _ensure_huggingface_hub()(token=self.token)
            api.snapshot_download(
                repo_id=self.model_id,
                local_dir=local_dir,
                allow_patterns=["LICENSE", "*.json", "*.md", "*.txt", "tokenizer.model"],
            )
        else:
            console.print("[bold green]Downloading model...")
            api = _ensure_huggingface_hub()(token=self.token)
            api.snapshot_download(
                repo_id=self.model_id,
                local_dir=local_dir,
            )

        # Convert to GGUF with specified outtype
        console.print(f"[bold green]Converting to {self.outtype}...")

        # Find the conversion script
        conversion_scripts = [
            "llama.cpp/convert_hf_to_gguf.py",
            "llama.cpp/convert-hf-to-gguf.py",
            "llama.cpp/convert.py",
        ]

        conversion_script = None
        for script in conversion_scripts:
            if os.path.isfile(script):
                conversion_script = script
                break

        if not conversion_script:
            raise ConversionError("Could not find HuggingFace to GGUF conversion script")

        # Use the appropriate Python executable
        python_cmd = "python" if platform.system() == "Windows" else "python3"

        # Build conversion command with new llama.cpp options
        convert_cmd = [
            python_cmd,
            conversion_script,
            str(local_dir),
            "--outtype",
            self.outtype,
            "--outfile",
            base_gguf,
        ]

        # Add optional flags based on new llama.cpp features
        if self.vocab_only:
            convert_cmd.append("--vocab-only")
        if self.no_lazy:
            convert_cmd.append("--no-lazy")
        if self.dry_run:
            convert_cmd.append("--dry-run")
        if self.remote:
            convert_cmd.extend(["--remote"])
        if self.model_name:
            convert_cmd.extend(["--model-name", self.model_name])
        if self.use_split:
            if self.split_max_tensors > 0:
                convert_cmd.extend(["--split-max-tensors", str(self.split_max_tensors)])
            if self.split_max_size:
                convert_cmd.extend(["--split-max-size", self.split_max_size])
        if self.small_first_shard:
            convert_cmd.append("--no-tensor-first-split")

        console.print(f"[cyan]Conversion command: {' '.join(convert_cmd)}")

        try:
            result = subprocess.run(convert_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise ConversionError(f"Error converting to {self.outtype}: {result.stderr}")
        except FileNotFoundError as e:
            raise ConversionError(f"Could not execute conversion script: {e}")

        if not os.path.isfile(base_gguf):
            raise ConversionError(f"Conversion completed but output file not found: {base_gguf}")

        console.print(f"[green]Model converted to {self.outtype} successfully!")

        # If base_only is True, we're done after base conversion (no quantization needed)
        if self.base_only:
            gguf_filename = f"{self.model_name}.{outtype_suffix}.gguf"
            quantized_files = [gguf_filename]
            if self.username and self.token:
                repo_id = f"{self.username}/{self.model_name}-GGUF"

                # Step 1: Create repository
                self.create_repository(repo_id)

                # Step 2: Upload README first
                readme_content = self.generate_readme(quantized_files)
                self.upload_readme(readme_content, repo_id)

                # Step 3: Upload model GGUF file
                console.print(f"[bold green]Uploading model file: {gguf_filename}")
                try:
                    api.upload_file(
                        path_or_fileobj=base_gguf, path_in_repo=gguf_filename, repo_id=repo_id
                    )
                    console.print(f"[green]✓ Successfully uploaded: {gguf_filename}")
                except Exception as e:
                    console.print(f"[red]✗ Failed to upload {gguf_filename}: {e}")
                    raise ConversionError(f"Error uploading model file: {e}")
            return

        # Generate importance matrix if needed
        imatrix_path: Optional[str] = None
        if self.use_imatrix:
            train_data_path = (
                self.train_data_file if self.train_data_file else "llama.cpp/groups_merged.txt"
            )
            imatrix_path = str(Path(outdir) / "imatrix.dat")
            self.generate_importance_matrix(base_gguf, train_data_path, imatrix_path)

        # Quantize model
        console.print("[bold green]Quantizing model...")
        quantized_files: List[str] = []
        quantize_binary = self.get_binary_path("llama-quantize")
        quantized_path = ""

        if not os.path.isfile(quantize_binary):
            raise ConversionError(f"llama-quantize binary not found at: {quantize_binary}")

        for method in self.quantization_methods:
            quantized_name = f"{self.model_name.lower()}-{method.lower()}"
            if self.use_imatrix:
                quantized_name += "-imat"
            quantized_path = str(Path(outdir) / f"{quantized_name}.gguf")

            console.print(f"[cyan]Quantizing with method: {method}")

            if self.use_imatrix and imatrix_path:
                quantize_cmd: List[str] = [
                    quantize_binary,
                    "--imatrix",
                    str(imatrix_path),
                    base_gguf,
                    quantized_path,
                    method,
                ]
            else:
                quantize_cmd = [quantize_binary, base_gguf, quantized_path, method]

            console.print(f"[cyan]Quantization command: {' '.join(quantize_cmd)}")

            try:
                result = subprocess.run(quantize_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise ConversionError(f"Error quantizing with {method}: {result.stderr}")
            except FileNotFoundError:
                raise ConversionError(f"Could not execute llama-quantize binary: {quantize_binary}")

            if not os.path.isfile(quantized_path):
                raise ConversionError(
                    f"Quantization completed but output file not found: {quantized_path}"
                )

            quantized_files.append(f"{quantized_name}.gguf")
            console.print(f"[green]Successfully quantized with {method}: {quantized_name}.gguf")

        # Upload to Hugging Face if credentials provided
        if self.username and self.token:
            repo_id = f"{self.username}/{self.model_name}-GGUF"

            # Step 1: Create repository
            console.print(f"[bold blue]Step 1: Creating repository {repo_id}")
            self.create_repository(repo_id)

            # Step 2: Generate and upload README first
            console.print("[bold blue]Step 2: Uploading README.md")
            readme_content = self.generate_readme(quantized_files)
            self.upload_readme(readme_content, repo_id)

            # Step 3: Upload model GGUF files
            console.print("[bold blue]Step 3: Upload model files")
            if self.use_split:
                split_files = self.split_model(quantized_path, outdir)
                self.upload_split_files(split_files, outdir, repo_id)
            else:
                # Upload single quantized file
                file_name = f"{self.model_name.lower()}-{self.quantization_methods[0].lower()}.gguf"
                console.print(f"[bold green]Uploading quantized model: {file_name}")
                try:
                    api.upload_file(
                        path_or_fileobj=quantized_path, path_in_repo=file_name, repo_id=repo_id
                    )
                    console.print(f"[green]✓ Successfully uploaded: {file_name}")
                except Exception as e:
                    console.print(f"[red]✗ Failed to upload {file_name}: {e}")
                    raise ConversionError(f"Error uploading quantized model: {e}")

            # Step 4: Upload imatrix if generated (optional)
            if imatrix_path:
                console.print("[bold blue]Step 4: Uploading importance matrix")
                console.print("[bold green]Uploading importance matrix: imatrix.dat")
                try:
                    api.upload_file(
                        path_or_fileobj=imatrix_path, path_in_repo="imatrix.dat", repo_id=repo_id
                    )
                    console.print("[green]✓ Successfully uploaded: imatrix.dat")
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to upload imatrix.dat: {e}")

            # Final success message
            console.print(f"[bold green]🎉 All files uploaded successfully to {repo_id}!")
            console.print(f"[cyan]Repository URL: https://huggingface.co/{repo_id}")


# Initialize CLI with HAI vibes
app = CLI(
    name="gguf", help="Convert HuggingFace models to GGUF format with style! 🔥", version="2.0.0"
)


@app.command(name="convert")
@option(
    "-m",
    "--model-id",
    help="The HuggingFace model ID (e.g., 'OEvortex/HelpingAI-Lite-1.5T')",
    required=True,
)
@option("-u", "--username", help="Your HuggingFace username for uploads", default=None)
@option("-t", "--token", help="Your HuggingFace API token for uploads", default=None)
@option("-q", "--quantization", help="Comma-separated quantization methods", default="q4_k_m")
@option(
    "-o", "--outtype", help="Output type: f32, f16, bf16, q8_0, tq1_0, tq2_0, auto", default="f16"
)
@option("-i", "--use-imatrix", help="Use importance matrix for quantization", is_flag=True)
@option("--train-data", help="Training data file for imatrix quantization", default=None)
@option("-s", "--split-model", help="Split the model into smaller chunks", is_flag=True)
@option(
    "--split-max-tensors", help="Maximum number of tensors per file when splitting", default=256
)
@option(
    "--split-max-size", help="Maximum file size when splitting (e.g., '256M', '5G')", default=None
)
@option("--vocab-only", help="Only extract vocabulary (no model weights)", is_flag=True)
@option("--remote", help="(Experimental) Read tensors remotely without full download", is_flag=True)
@option("--dry-run", help="Only print split plan without writing files", is_flag=True)
@option("--no-lazy", help="Disable lazy evaluation (use more RAM)", is_flag=True)
@option("--model-name", help="Custom model name override", default=None)
@option("--small-first-shard", help="Do not add tensors to the first split", is_flag=True)
def convert_command(
    model_id: str,
    username: Optional[str] = None,
    token: Optional[str] = None,
    quantization: str = "q4_k_m",
    outtype: str = "f16",
    use_imatrix: bool = False,
    train_data: Optional[str] = None,
    split_model: bool = False,
    split_max_tensors: int = 256,
    split_max_size: Optional[str] = None,
    vocab_only: bool = False,
    remote: bool = False,
    dry_run: bool = False,
    no_lazy: bool = False,
    model_name: Optional[str] = None,
    small_first_shard: bool = False,
) -> None:
    """
    Convert and quantize HuggingFace models to GGUF format! 🚀

    Args:
        model_id (str): Your model's HF ID (like 'OEvortex/HelpingAI-Lite-1.5T') 🎯
        username (str, optional): Your HF username for uploads 👤
        token (str, optional): Your HF API token 🔑
        quantization (str): Quantization methods (default: q4_k_m) 🎮
        outtype (str): Output type: f32, f16, bf16, q8_0, tq1_0, tq2_0, auto 📊
        use_imatrix (bool): Use importance matrix for quantization 🔍
        train_data (str, optional): Training data file for imatrix quantization 📚
        split_model (bool): Split the model into smaller chunks 🔪
        split_max_tensors (int): Max tensors per file when splitting (default: 256) 📊
        split_max_size (str, optional): Max file size when splitting (e.g., '256M', '5G') 📏
        vocab_only (bool): Only extract vocabulary (no model weights) 📖
        remote (bool): (Experimental) Read tensors remotely without full download 🌐
        dry_run (bool): Only print split plan without writing files 📝
        no_lazy (bool): Disable lazy evaluation (use more RAM) 🧠
        model_name (str, optional): Custom model name override 🏷️
        small_first_shard (bool): Do not add tensors to the first split 📦

    Example:
        >>> python -m llm4free.Extra.gguf convert \\
        ...     -m "OEvortex/HelpingAI-Lite-1.5T" \\
        ...     -q "q4_k_m,q5_k_m" \\
        ...     -o "f16"
    """
    try:
        converter = ModelConverter(
            model_id=model_id,
            username=username,
            token=token,
            quantization_methods=quantization,
            use_imatrix=use_imatrix,
            train_data_file=train_data,
            split_model=split_model,
            split_max_tensors=split_max_tensors,
            split_max_size=split_max_size,
            outtype=outtype,
            vocab_only=vocab_only,
            remote=remote,
            dry_run=dry_run,
            no_lazy=no_lazy,
            model_name=model_name,
            small_first_shard=small_first_shard,
        )
        converter.convert()
    except (ConversionError, ValueError) as e:
        console.print(f"[red]Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}")
        sys.exit(1)


def main() -> None:
    """Fire up the GGUF converter! 🚀"""
    app.run()


if __name__ == "__main__":
    main()
